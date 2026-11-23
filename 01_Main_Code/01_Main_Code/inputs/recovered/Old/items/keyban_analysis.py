#!/usr/bin/env python3
"""
KEY-BAN NATURAL EXPERIMENT — H1, H2, H3
Implements KeyBan_Natural_Experiment_PreRegistration.

HOW TO USE:
  1. Save this file INTO the folder containing the 22,495 item CSVs.
  2. Double-click it (or: python keyban_analysis.py).
  3. Send the outputs to Claude:
        keyban_results.txt
        keyban_daily_panel.csv
        keyban_event_study.csv

NOT YET TESTED against key/case series — no key data has been examined.
Treat the first run as a debugging run. Report errors verbatim.

Requires: pandas, numpy, statsmodels  (pip install pandas numpy statsmodels)
"""

import os, sys, glob, urllib.parse, warnings
warnings.filterwarnings("ignore")

try:
    import numpy as np
    import pandas as pd
    import statsmodels.formula.api as smf
except ImportError:
    print("\nMissing libraries. Run:\n    pip install pandas numpy statsmodels\n")
    input("Press Enter to close...")
    sys.exit(1)

HERE = os.path.dirname(os.path.abspath(__file__))
BAN = pd.Timestamp("2019-10-28", tz="UTC")          # Valve key trade-lock
SHATTERED_WEB = pd.Timestamp("2019-11-18", tz="UTC")  # confound
WEAR = ("Factory New", "Minimal Wear", "Field-Tested", "Well-Worn", "Battle-Scarred")
FUNGIBLE_TERMS = ("Case", "Capsule", "Graffiti", "Sticker", "Package", "Pin")
SKIP = {"cs2_item_aggregates.csv", "cs2_verification_log.txt", "name_conversion_table.csv",
        "example price history.csv", "keyban_daily_panel.csv", "keyban_event_study.csv"}


def item_name(path):
    b = os.path.basename(path)
    b = b[:-4] if b.lower().endswith(".csv") else b
    if "___" in b:
        b = b.split("___", 1)[1]
    return urllib.parse.unquote(b.replace("_", "%"))


def classify(name):
    """Assign each item to: key | substitute-candidate | control | excluded.
    Rule fixed ex ante — see pre-registration §4. Do not tune after seeing results."""
    n = name
    if "Key" in n:
        return "key"
    is_wear = any(w in n for w in WEAR)
    is_fungible = (not is_wear) and any(t in n for t in FUNGIBLE_TERMS)
    if is_fungible:
        return "substitute_candidate"   # price/volume filters applied later
    if is_wear:
        return "control_candidate"      # price filter applied later
    return "excluded"


def find_cols(df):
    p = q = t = None
    for c in df.columns:
        lc = c.strip().lower()
        if p is None and "price" in lc: p = c
        elif q is None and ("quantity" in lc or lc in ("qty", "volume")): q = c
        elif t is None and ("unix" in lc or "timestamp" in lc): t = c
    return p, q, t


def main():
    files = [f for f in sorted(glob.glob(os.path.join(HERE, "*.csv")))
             if os.path.basename(f).lower() not in {s.lower() for s in SKIP}]
    print("=" * 66)
    print("KEY-BAN NATURAL EXPERIMENT")
    print("=" * 66)
    print(f"Folder: {HERE}\nCSVs:   {len(files):,}\n")
    if not files:
        print("No CSVs found. Save this script INTO the item-CSV folder.")
        input("\nPress Enter..."); return

    rows = []
    for i, f in enumerate(files, 1):
        if i % 1000 == 0:
            print(f"  {i:,}/{len(files):,}...", flush=True)
        try:
            d = pd.read_csv(f)
            p, q, t = find_cols(d)
            if not all([p, q, t]):
                continue
            d = d[[p, q, t]].rename(columns={p: "price", q: "quantity", t: "ts"})
            d["price"] = pd.to_numeric(d["price"], errors="coerce")
            d["quantity"] = pd.to_numeric(d["quantity"], errors="coerce")
            d["ts"] = pd.to_numeric(d["ts"], errors="coerce")
            d = d.dropna()
            if d.empty:
                continue
        except Exception:
            continue

        name = item_name(f)
        grp = classify(name)
        if grp == "excluded":
            continue
        d["day"] = pd.to_datetime(d["ts"], unit="s", utc=True).dt.floor("D")
        daily = d.groupby("day").agg(
            units=("quantity", "sum"),
            vwap=("price", lambda s: np.nan)).reset_index()
        # volume-weighted price per day
        vw = d.groupby("day").apply(
            lambda g: np.average(g["price"], weights=g["quantity"]) if g["quantity"].sum() else np.nan)
        daily["vwap"] = daily["day"].map(vw)
        daily["item"] = name
        daily["group"] = grp
        rows.append(daily)

    if not rows:
        print("No usable series."); input("\nPress Enter..."); return
    panel = pd.concat(rows, ignore_index=True).dropna(subset=["vwap"])

    # ---- apply pre-registered price/liquidity filters using PRE-period only ----
    pre = panel[panel["day"] < BAN]
    stats = pre.groupby("item").agg(med_price=("vwap", "median"),
                                    med_units=("units", "median"),
                                    n_obs=("day", "count"))
    liq_cut = stats["med_units"].quantile(0.75)

    subs = set(stats[(stats.index.map(lambda x: classify(x) == "substitute_candidate")) &
                     (stats["med_price"] < 10) &
                     (stats["med_units"] > liq_cut) &
                     (stats["n_obs"] >= 180)].index)
    ctrl = set(stats[(stats.index.map(lambda x: classify(x) == "control_candidate")) &
                     (stats["med_price"] > 50) &
                     (stats["n_obs"] >= 180)].index)
    keys = set(stats[stats.index.map(lambda x: classify(x) == "key")].index)

    def grp(i):
        return "key" if i in keys else ("substitute" if i in subs else ("control" if i in ctrl else None))
    panel["arm"] = panel["item"].map(grp)
    panel = panel.dropna(subset=["arm"])
    panel.to_csv(os.path.join(HERE, "keyban_daily_panel.csv"), index=False)

    L = []
    def P(s=""):
        print(s); L.append(s)

    P(f"Liquidity cut (75th pct pre-period median daily units): {liq_cut:.1f}")
    P(f"Arms — keys: {len(keys)} | substitutes: {len(subs)} | controls: {len(ctrl)}\n")

    # ================= H1: pre-ban anomalous accumulation =================
    P("=" * 66); P("H1 — PRE-BAN ACCUMULATION (keys vs substitute baseline)"); P("=" * 66)
    m = panel[panel["day"] < BAN].copy()
    m["month"] = m["day"].dt.to_period("M")
    kv = m[m["arm"] == "key"].groupby("month")["units"].sum()
    sv = m[m["arm"] == "substitute"].groupby("month")["units"].sum()
    ratio = (kv / sv).dropna()
    if len(ratio) > 12:
        base = ratio[ratio.index < "2018-10"].mean()
        last12 = ratio[ratio.index >= "2018-10"].mean()
        P(f"  Key:substitute volume ratio, baseline (to Oct-2018): {base:.4f}")
        P(f"  Key:substitute volume ratio, final 12 months:        {last12:.4f}")
        P(f"  Ratio change: {(last12/base - 1)*100:+.1f}%   [H1 predicts a marked positive divergence]")
    P("\n  Monthly key:substitute ratio (last 24 pre-ban months):")
    for mo, v in ratio.tail(24).items():
        P(f"    {mo}: {v:.4f}")

    # ================= H2: displacement (DiD) =================
    P("\n" + "=" * 66); P("H2 — DISPLACEMENT (substitutes vs controls, DiD)"); P("=" * 66)
    for label, win in (("PRIMARY  ±21d (excludes Shattered Web)", 21),
                       ("SECONDARY ±90d (confounded by Shattered Web)", 90)):
        d = panel[(panel["arm"] != "key") &
                  (panel["day"] >= BAN - pd.Timedelta(days=win)) &
                  (panel["day"] <= BAN + pd.Timedelta(days=win))].copy()
        if d.empty:
            P(f"\n  {label}: no data"); continue
        d["post"] = (d["day"] >= BAN).astype(int)
        d["treat"] = (d["arm"] == "substitute").astype(int)
        d["lunits"] = np.log1p(d["units"])
        try:
            fit = smf.ols("lunits ~ post * treat + C(item)", data=d).fit(
                cov_type="cluster", cov_kwds={"groups": d["item"]})
            b = fit.params.get("post:treat", np.nan)
            se = fit.bse.get("post:treat", np.nan)
            p_ = fit.pvalues.get("post:treat", np.nan)
            P(f"\n  {label}")
            P(f"    DiD coefficient (post x treat): {b:+.4f}  (SE {se:.4f}, p={p_:.4f})")
            P(f"    -> implies {(np.exp(b)-1)*100:+.1f}% volume change in substitutes vs controls")
            P(f"    H2 predicts POSITIVE. Null/negative => displacement NOT supported.")
        except Exception as e:
            P(f"\n  {label}: model failed — {e}")

    # ---- event study: daily leads/lags ----
    P("\n  Event study (daily, substitutes minus controls, log units):")
    es = []
    for off in range(-45, 46):
        day = BAN + pd.Timedelta(days=off)
        dd = panel[panel["day"] == day]
        if dd.empty: continue
        s = np.log1p(dd[dd["arm"] == "substitute"]["units"]).mean()
        c = np.log1p(dd[dd["arm"] == "control"]["units"]).mean()
        es.append({"offset": off, "date": day.date(), "sub": s, "ctrl": c, "diff": s - c})
    ES = pd.DataFrame(es)
    ES.to_csv(os.path.join(HERE, "keyban_event_study.csv"), index=False)
    if len(ES):
        P(f"    Mean diff, t-45..t-1 (pre-trend, should be FLAT): {ES[ES.offset<0]['diff'].mean():+.4f}")
        P(f"    Mean diff, t+1..t+21:                             {ES[(ES.offset>0)&(ES.offset<=21)]['diff'].mean():+.4f}")
        P("    (full series written to keyban_event_study.csv — plot this; it is Figure 2)")

    # ---- placebo tests ----
    P("\n  PLACEBO (identical DiD at non-event dates; significance here invalidates design):")
    for pdate in ("2017-06-15", "2018-03-20", "2018-09-10"):
        pt = pd.Timestamp(pdate, tz="UTC")
        d = panel[(panel["arm"] != "key") &
                  (panel["day"] >= pt - pd.Timedelta(days=21)) &
                  (panel["day"] <= pt + pd.Timedelta(days=21))].copy()
        if len(d) < 100:
            P(f"    {pdate}: insufficient data"); continue
        d["post"] = (d["day"] >= pt).astype(int)
        d["treat"] = (d["arm"] == "substitute").astype(int)
        d["lunits"] = np.log1p(d["units"])
        try:
            f2 = smf.ols("lunits ~ post * treat + C(item)", data=d).fit(
                cov_type="cluster", cov_kwds={"groups": d["item"]})
            P(f"    {pdate}: DiD {f2.params.get('post:treat', np.nan):+.4f} (p={f2.pvalues.get('post:treat', np.nan):.3f})")
        except Exception:
            P(f"    {pdate}: model failed")

    # ================= H3: legacy scarcity premium =================
    P("\n" + "=" * 66); P("H3 — LEGACY KEY SCARCITY PREMIUM"); P("=" * 66)
    kp = panel[panel["arm"] == "key"].groupby("day")["vwap"].mean()
    fp = panel[panel["arm"] == "substitute"].groupby("day")["vwap"].mean()
    for yr in range(2018, 2025):
        k = kp[kp.index.year == yr].mean()
        f = fp[fp.index.year == yr].mean()
        if not np.isnan(k):
            P(f"    {yr}: mean key price {k:8.2f} | fungible index {f:6.2f} | ratio {k/f if f else float('nan'):6.2f}")
    P("\n    H3 predicts key price rising persistently vs the fungible index after Oct-2019.")
    P("    Rival (collector demand) predicts a premium tracking the index.")

    with open(os.path.join(HERE, "keyban_results.txt"), "w") as fh:
        fh.write("\n".join(L))
    print("\n" + "=" * 66)
    print("DONE. Written: keyban_results.txt, keyban_daily_panel.csv, keyban_event_study.csv")
    print("=" * 66)
    input("\nPress Enter to close...")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback; traceback.print_exc()
        input("\nError above — copy it and send. Press Enter to close...")
