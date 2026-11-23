#!/usr/bin/env python3
"""
CS2 corpus verification -- Section 4.1.1 of "The Hidden Laundromat".

HOW TO USE:
  1. Save this file INTO the folder that contains the item CSV files.
  2. Double-click it.  (No command line, no paths needed.)
  3. Wait. It prints progress and pauses at the end so you can read the results.
  4. Send me the two files it writes:
        cs2_item_aggregates.csv
        cs2_verification_log.txt
"""

import os, sys, glob, urllib.parse, warnings

warnings.filterwarnings("ignore")

# ---- Friendly startup: check libraries before doing anything else ----------
try:
    import numpy as np
    import pandas as pd
except ImportError:
    print("\nMissing libraries. Open Command Prompt and run:\n")
    print("    pip install pandas numpy\n")
    input("Press Enter to close...")
    sys.exit(1)

SPIKE_PCT = 1.00         # ">100%" day-over-day
SPIKE_MEANPRICE = 10.0   # "items with average prices above USD 10"
HIGH_VALUE = 100.0       # "items priced above USD 100"
THRESH = 1000.0          # the 1,000 threshold (currency question flagged below)
KNIFE_TERMS = ("knife", "bayonet", "karambit", "daggers", "dagger")

# The folder this script is sitting in:
HERE = os.path.dirname(os.path.abspath(__file__))
SKIP = {"cs2_item_aggregates.csv", "cs2_spike_rules.csv",
        "name_conversion_table.csv", "example price history.csv"}


def item_name(path):
    b = os.path.basename(path)
    b = b[:-4] if b.lower().endswith(".csv") else b
    if "___" in b:
        b = b.split("___", 1)[1]
    return urllib.parse.unquote(b.replace("_", "%"))


def find_cols(df):
    """Locate price / quantity / timestamp columns whatever they're called."""
    price = qty = ts = None
    for c in df.columns:
        lc = c.strip().lower()
        if price is None and "price" in lc:
            price = c
        elif qty is None and ("quantity" in lc or lc in ("qty", "volume", "count")):
            qty = c
        elif ts is None and ("unix" in lc or "timestamp" in lc or lc == "time"):
            ts = c
    if ts is None:
        for c in df.columns:
            if "date" in c.strip().lower():
                ts = c
                break
    return price, qty, ts


def main():
    files = [f for f in sorted(glob.glob(os.path.join(HERE, "*.csv")))
             if os.path.basename(f).lower() not in SKIP]
    print("=" * 66)
    print("CS2 VERIFICATION")
    print("=" * 66)
    print(f"Folder : {HERE}")
    print(f"CSVs   : {len(files):,}\n")

    if not files:
        print("No CSV files found in this folder.")
        print("Make sure this script is saved INTO the folder with the item CSVs.")
        input("\nPress Enter to close...")
        return

    # Show the schema of the first file so mismatches surface immediately
    probe = pd.read_csv(files[0], nrows=3)
    pc, qc, tc = find_cols(probe)
    print(f"Detected columns -> price: {pc!r} | quantity: {qc!r} | timestamp: {tc!r}")
    if not all([pc, qc, tc]):
        print(f"\nCould not identify the needed columns. Found: {list(probe.columns)}")
        input("\nPress Enter to close...")
        return
    print()

    rows = []
    units_over_100 = value_over_100 = 0.0
    obs_over_thresh = total_units = total_obs = 0
    total_value = 0.0
    spike_hits = spike_eligible = 0
    items_top10 = items_over_1000 = 0
    knife_units = knife_items = 0
    knife_value = 0.0
    min_ts = max_ts = None
    bad = 0

    for i, f in enumerate(files, 1):
        if i % 500 == 0:
            print(f"  {i:,}/{len(files):,}...", flush=True)
        try:
            d = pd.read_csv(f)
            p, q, t = find_cols(d)
            d = d[[p, q, t]].rename(columns={p: "price", q: "quantity", t: "ts"})
            d["price"] = pd.to_numeric(d["price"], errors="coerce")
            d["quantity"] = pd.to_numeric(d["quantity"], errors="coerce")
            d["ts"] = pd.to_numeric(d["ts"], errors="coerce")
            d = d.dropna()
            if d.empty:
                bad += 1
                continue
        except Exception:
            bad += 1
            continue

        name = item_name(f)
        d = d.sort_values("ts")
        val = d["price"] * d["quantity"]
        u, v, n = int(d["quantity"].sum()), float(val.sum()), len(d)
        total_units += u; total_value += v; total_obs += n

        lo, hi = int(d["ts"].min()), int(d["ts"].max())
        min_ts = lo if min_ts is None else min(min_ts, lo)
        max_ts = hi if max_ts is None else max(max_ts, hi)

        hv = d["price"] > HIGH_VALUE
        units_over_100 += float(d.loc[hv, "quantity"].sum())
        value_over_100 += float(val[hv].sum())
        n_over = int((d["price"] > THRESH).sum())
        obs_over_thresh += n_over
        if n_over:
            items_over_1000 += 1

        is_knife = any(k in name.lower() for k in KNIFE_TERMS)
        if is_knife:
            knife_items += 1; knife_units += u; knife_value += v

        if n >= 10:
            cut = d["price"].quantile(0.90)
            if val[d["price"] >= cut].sum() > 0.5 * v:
                items_top10 += 1

        mean_price = float(d["price"].mean())
        if mean_price > SPIKE_MEANPRICE:
            spike_eligible += 1
            day = pd.to_datetime(d["ts"], unit="s", utc=True).dt.floor("D")
            daily = d.assign(day=day).groupby("day").apply(
                lambda g: np.average(g["price"], weights=g["quantity"])
                if g["quantity"].sum() else np.nan).dropna()
            if len(daily) > 1:
                spike_hits += int((daily.pct_change().abs() > SPIKE_PCT).sum())

        rows.append({"item": name, "observations": n, "total_units": u,
                     "gross_value": v, "mean_price": mean_price,
                     "median_price": float(d["price"].median()),
                     "max_price": float(d["price"].max()),
                     "obs_over_1000": n_over, "is_knife": is_knife,
                     "first_ts": lo, "last_ts": hi})

    agg = pd.DataFrame(rows)
    out_agg = os.path.join(HERE, "cs2_item_aggregates.csv")
    agg.to_csv(out_agg, index=False)
    top100 = agg.nlargest(100, "gross_value")["gross_value"].sum()

    L = []
    def p(s=""):
        print(s); L.append(s)

    p("\n" + "=" * 66)
    p("SECTION 4.1.1 VERIFICATION")
    p("=" * 66)
    p(f"{'CLAIM':<44}{'FOUND':>22}")
    p("-" * 66)
    p(f"{'22,495 unique tradeable items':<44}{len(agg):>22,}")
    p(f"{'~105 million price observations':<44}{total_obs:>22,}")
    p(f"{'~5.85 billion recorded unit sales':<44}{total_units:>22,}")
    p(f"{'spanning 2016 to 2024':<44}"
      f"{str(pd.to_datetime(min_ts, unit='s').date())+' to '+str(pd.to_datetime(max_ts, unit='s').date()):>22}")
    p(f"{'>$100: 0.1% of units':<44}{units_over_100/max(total_units,1):>21.3%}")
    p(f"{'>$100: 22.7% of value':<44}{value_over_100/max(total_value,1):>21.2%}")
    p(f"{'>$100: ~USD 1.31 billion':<44}{value_over_100:>22,.0f}")
    p(f"{'874 items traded above 1,000':<44}{items_over_1000:>22,}")
    p(f"{'>32,000 obs exceed 1,000':<44}{obs_over_thresh:>22,}")
    p(f"{'knives/blades: 3,274 items':<44}{knife_items:>22,}")
    p(f"{'knives: 22.1% of value':<44}{knife_value/max(total_value,1):>21.2%}")
    p(f"{'knives: ~USD 1.28 billion':<44}{knife_value:>22,.0f}")
    p(f"{'knives: 0.24% of unit volume':<44}{knife_units/max(total_units,1):>21.3%}")
    p(f"{'knives: avg price USD 90.38':<44}{knife_value/max(knife_units,1):>22,.2f}")
    p(f"{'25,432 day-over-day spikes >100%':<44}{spike_hits:>22,}")
    p(f"{'   eligible items (mean price > $10)':<44}{spike_eligible:>22,}")
    p(f"{'1,011 items: top 10% obs > 50% value':<44}{items_top10:>22,}")
    p(f"{'top 100 items = 23.9% of value':<44}{top100/max(total_value,1):>21.2%}")
    p("-" * 66)
    p(f"{'total transacted value':<44}{total_value:>22,.0f}")
    if bad:
        p(f"{'files skipped (unreadable/empty)':<44}{bad:>22,}")

    p("\nConcentration sensitivity (share of value):")
    for n in (10, 50, 100, 200, 500, 1000):
        if n <= len(agg):
            p(f"   top-{n:<5}: {agg.nlargest(n,'gross_value')['gross_value'].sum()/total_value:7.2%}")

    p("\nNOTE: the 1,000 threshold is applied in the dataset's native currency.")
    p("If prices are USD, this is a USD 1,000 count, not the EUR 1,000 AMLR threshold.")

    with open(os.path.join(HERE, "cs2_verification_log.txt"), "w") as fh:
        fh.write("\n".join(L))

    print("\n" + "=" * 66)
    print("DONE. Two files written into this folder:")
    print("   cs2_item_aggregates.csv")
    print("   cs2_verification_log.txt")
    print("Send both to Claude.")
    print("=" * 66)
    input("\nPress Enter to close...")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        traceback.print_exc()
        input("\nSomething went wrong. Copy the text above and send it. Press Enter to close...")
