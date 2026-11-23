#!/usr/bin/env python3
"""
S1b — THE FUNGIBLE-ITEMS SPIKE TEST
Implements Laundering_Signature_Prespecification, Section S1b.

QUESTION: Do anomalous price spikes persist in GENUINELY FUNGIBLE items
(cases, capsules, stickers, graffiti) — where within-name float/pattern
heterogeneity CANNOT explain dispersion — at rates above a
liquidity-matched non-fungible baseline?

COMMITTED PREDICTIONS (fixed before this script was run):
  Laundering  -> idiosyncratic, thin, RAPIDLY REVERTING spikes persist in
                 fungible items above the liquidity-matched baseline.
  Rival       -> with heterogeneity removed, anomalous spikes largely
                 vanish; residual dispersion tracks liquidity; reversion
                 stays low.
  Falsifier   -> fungible spike rates at/below the liquidity-matched
                 baseline => the price-anomaly evidence is WITHDRAWN as
                 laundering evidence. Report either way.

HOW TO USE:
  1. Save this file INTO the folder containing the 22,495 item CSVs.
  2. Double-click it (or: python s1b_analysis.py).
  3. Send back:  s1b_results.txt  and  s1b_spikes.csv

Requires: pandas, numpy   (pip install pandas numpy)
"""

import os, sys, glob, urllib.parse, warnings
warnings.filterwarnings("ignore")

try:
    import numpy as np
    import pandas as pd
except ImportError:
    print("\nMissing libraries. Run:\n    pip install pandas numpy\n")
    input("Press Enter to close...")
    sys.exit(1)

HERE = os.path.dirname(os.path.abspath(__file__))

SPIKE_PCT = 1.00          # ">100%" day-over-day (same rule as Section 4.1.1)
MEANPRICE_MIN = 10.0      # primary analysis keeps the original >$10 filter
REVERT_BAND = 0.25        # reversion = VWAP back within +/-25% of pre-spike level
REVERT_DAYS = 3           # ...within 3 days
PEER_IDIO = 0.10          # idiosyncratic = |peer median return| < 10% that day

WEAR = ("Factory New", "Minimal Wear", "Field-Tested", "Well-Worn", "Battle-Scarred")
FUNGIBLE_TERMS = ("Case", "Capsule", "Sticker", "Graffiti", "Package", "Pin", "Patch")
SKIP = {"cs2_item_aggregates.csv", "cs2_verification_log.txt", "name_conversion_table.csv",
        "example price history.csv", "keyban_daily_panel.csv", "keyban_event_study.csv",
        "keyban_results.txt", "s1b_spikes.csv", "s1b_results.txt"}


def item_name(path):
    b = os.path.basename(path)
    b = b[:-4] if b.lower().endswith(".csv") else b
    if "___" in b:
        b = b.split("___", 1)[1]
    return urllib.parse.unquote(b.replace("_", "%"))


def classify(name):
    """fungible | nonfungible | excluded. Fixed ex ante; do not tune."""
    if "Key" in name:
        return "excluded"                      # keys analyzed separately (key-ban study)
    if any(w in name for w in WEAR):
        return "nonfungible"                   # float/pattern heterogeneity possible
    if any(t in name for t in FUNGIBLE_TERMS):
        return "fungible"                      # identical units; heterogeneity impossible
    return "excluded"                          # agents, music kits, misc.


def subclass(name):
    """Peer group for co-movement, within the fungible arm."""
    for t in ("Case", "Capsule", "Sticker", "Graffiti", "Package", "Pin", "Patch"):
        if t in name:
            return t
    return "Other"


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
    print("S1b — FUNGIBLE-ITEMS SPIKE TEST")
    print("=" * 66)
    print(f"Folder: {HERE}\nCSVs:   {len(files):,}\n")
    if not files:
        print("No CSVs found. Save this script INTO the item-CSV folder.")
        input("\nPress Enter..."); return

    # ---------- pass 1: build daily VWAP series per eligible item ----------
    series = {}      # name -> DataFrame(day, vwap, units)
    meta = {}        # name -> dict(arm, sub, mean_price, med_units)
    for i, f in enumerate(files, 1):
        if i % 1000 == 0:
            print(f"  {i:,}/{len(files):,}...", flush=True)
        name = item_name(f)
        arm = classify(name)
        if arm == "excluded":
            continue
        try:
            d = pd.read_csv(f)
            p, q, t = find_cols(d)
            if not all([p, q, t]):
                continue
            d = d[[p, q, t]].rename(columns={p: "price", q: "quantity", t: "ts"})
            for c in ("price", "quantity", "ts"):
                d[c] = pd.to_numeric(d[c], errors="coerce")
            d = d.dropna()
            if len(d) < 30:
                continue
        except Exception:
            continue

        mean_price = float(d["price"].mean())
        d["day"] = pd.to_datetime(d["ts"], unit="s", utc=True).dt.floor("D")
        g = d.groupby("day")
        daily = pd.DataFrame({
            "units": g["quantity"].sum(),
            "vwap": g.apply(lambda x: np.average(x["price"], weights=x["quantity"])
                            if x["quantity"].sum() else np.nan)
        }).dropna()
        if len(daily) < 30:
            continue
        series[name] = daily
        meta[name] = {"arm": arm, "sub": subclass(name) if arm == "fungible" else "NF",
                      "mean_price": mean_price,
                      "med_units": float(daily["units"].median())}

    if not series:
        print("No usable series."); input("\nPress Enter..."); return
    print(f"\nEligible series: {len(series):,} "
          f"(fungible {sum(1 for m in meta.values() if m['arm']=='fungible'):,} | "
          f"nonfungible {sum(1 for m in meta.values() if m['arm']=='nonfungible'):,})")

    # ---------- peer return indices (median daily return per group) ----------
    print("Building peer indices...")
    ret_frames = {}
    for name, daily in series.items():
        r = daily["vwap"].pct_change()
        r.name = name
        ret_frames.setdefault(meta[name]["sub"] if meta[name]["arm"] == "fungible" else "NF",
                              []).append(r)
    peer_median = {grp: pd.concat(rs, axis=1).median(axis=1)
                   for grp, rs in ret_frames.items()}

    # ---------- spike detection ----------
    print("Detecting spikes...")
    spikes = []
    item_days = {"fungible": 0, "nonfungible": 0}
    item_days_p10 = {"fungible": 0, "nonfungible": 0}
    for name, daily in series.items():
        arm = meta[name]["arm"]
        eligible_p10 = meta[name]["mean_price"] > MEANPRICE_MIN
        n_days = len(daily)
        item_days[arm] += n_days
        if eligible_p10:
            item_days_p10[arm] += n_days
        r = daily["vwap"].pct_change()
        hits = r[r > SPIKE_PCT]
        if hits.empty:
            continue
        pgrp = meta[name]["sub"] if arm == "fungible" else "NF"
        pm = peer_median.get(pgrp)
        idx = daily.index
        for day, ret in hits.items():
            pos = idx.get_loc(day)
            pre = daily["vwap"].iloc[pos - 1] if pos >= 1 else np.nan
            # reversion: any of next REVERT_DAYS observed days back within band of pre level
            reverted = False
            j = pos + 1
            while j < len(idx) and (idx[j] - day).days <= REVERT_DAYS:
                if abs(daily["vwap"].iloc[j] - pre) / pre <= REVERT_BAND:
                    reverted = True
                    break
                j += 1
            peer_r = float(pm.loc[day]) if (pm is not None and day in pm.index) else np.nan
            spikes.append({
                "item": name, "arm": arm, "peer_group": pgrp, "day": day.date(),
                "ret": float(ret), "units_at_spike": float(daily["units"].iloc[pos]),
                "pre_vwap": float(pre), "spike_vwap": float(daily["vwap"].iloc[pos]),
                "peer_median_ret": peer_r,
                "idiosyncratic": bool(abs(peer_r) < PEER_IDIO) if not np.isnan(peer_r) else None,
                "reverted_3d": reverted,
                "mean_price_gt10": eligible_p10,
                "item_med_units": meta[name]["med_units"],
            })

    S = pd.DataFrame(spikes)
    S.to_csv(os.path.join(HERE, "s1b_spikes.csv"), index=False)

    # ---------- reporting ----------
    L = []
    def P(s=""):
        print(s); L.append(s)

    def block(df, label, idays):
        P(f"\n  {label}")
        if df.empty or idays == 0:
            P("    no spikes / no eligible item-days"); return
        n = len(df)
        P(f"    spikes: {n:,}   item-days: {idays:,}   "
          f"rate: {1000*n/idays:.3f} per 1,000 item-days")
        idio = df["idiosyncratic"].dropna()
        P(f"    idiosyncratic (peer moved <10%): {idio.mean()*100:.1f}%" if len(idio) else
          "    idiosyncratic: n/a")
        P(f"    median units at spike: {df['units_at_spike'].median():.0f}")
        P(f"    reversion within {REVERT_DAYS}d (+/-{int(REVERT_BAND*100)}% of pre level): "
          f"{df['reverted_3d'].mean()*100:.1f}%")

    P("=" * 66); P("S1b RESULTS"); P("=" * 66)
    P("\nPRIMARY — original Section 4.1.1 rule (mean price > USD 10):")
    block(S[(S.arm == "fungible") & S.mean_price_gt10], "FUNGIBLE (cases/capsules/stickers/graffiti)",
          item_days_p10["fungible"])
    block(S[(S.arm == "nonfungible") & S.mean_price_gt10], "NON-FUNGIBLE (wear-designated skins/knives)",
          item_days_p10["nonfungible"])

    P("\nSECONDARY — all price levels (no $10 filter):")
    block(S[S.arm == "fungible"], "FUNGIBLE", item_days["fungible"])
    block(S[S.arm == "nonfungible"], "NON-FUNGIBLE", item_days["nonfungible"])

    # liquidity-matched comparison: spike rate by item-liquidity quintile
    P("\nLIQUIDITY-MATCHED COMPARISON (spike rate per 1,000 item-days, by")
    P("quintile of item median daily units, computed on the pooled corpus):")
    liq = pd.Series({n: m["med_units"] for n, m in meta.items()})
    qs = liq.quantile([0.2, 0.4, 0.6, 0.8]).values
    def quint(v):
        return int(np.searchsorted(qs, v, side="right"))
    days_by = {}
    for n, daily in series.items():
        key = (meta[n]["arm"], quint(meta[n]["med_units"]))
        days_by[key] = days_by.get(key, 0) + len(daily)
    if not S.empty:
        S["liq_q"] = S["item_med_units"].map(quint)
    P(f"    {'quintile':<10}{'fungible':>14}{'nonfungible':>14}")
    for q in range(5):
        row = []
        for arm in ("fungible", "nonfungible"):
            nd = days_by.get((arm, q), 0)
            ns = 0 if S.empty else len(S[(S.arm == arm) & (S.liq_q == q)])
            row.append(f"{1000*ns/nd:.3f}" if nd else "—")
        P(f"    Q{q+1:<9}{row[0]:>14}{row[1]:>14}")

    P("\nDECISION RULE (committed in Laundering_Signature_Prespecification):")
    P("  Laundering signature requires, in FUNGIBLE items: spike rates ABOVE the")
    P("  liquidity-matched non-fungible baseline AND materially higher reversion")
    P("  than the ~9% observed in the heterogeneity-driven prototype.")
    P("  Fungible rates at/below baseline, or persistently low reversion,")
    P("  => the price-anomaly evidence is withdrawn as laundering evidence.")
    P("\n  Interpret nothing here alone — send both output files back for the")
    P("  write-up so exploratory vs confirmatory status is preserved.")

    with open(os.path.join(HERE, "s1b_results.txt"), "w") as fh:
        fh.write("\n".join(L))
    print("\n" + "=" * 66)
    print("DONE. Written: s1b_results.txt, s1b_spikes.csv")
    print("=" * 66)
    input("\nPress Enter to close...")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback; traceback.print_exc()
        input("\nError above — copy it and send. Press Enter to close...")
