# Execution and discrepancy report: COSE v48

The public-market reproduction completed in a fresh Python environment and a new raw-data directory. All **352 final summaries and 6,608 recovery-curve rows** agree with v48 within the frozen comparison tolerances. The comparison covers nine supplementary result tables plus Figure 4 data: 306 field checks, zero differing cells or row keys. An additional 71 S3.8 audit/cohort comparisons match. The selected full cohort and principal H2 estimates reproduce; 35% and 50% remain the first qualifying abrupt-response grid doses.

This is a successful local raw-to-results execution, not a certification that every v48 statement or graphic reproduces. The S1b total and some H3 prices differ; the SteamDB source needed for Figures 2 and 3 is absent. Those limits must accompany any reviewer claim. No manuscript, workbook, prior result, scientific specification or GitHub repository was changed.

## What was executed

The Downloads ZIP has SHA-256 `e00557bd8dc6d5e1a09f8da36213039ac23950f9613e245db49c6ef564ce6df7`. All 22,497 CSV members passed hash verification after fresh extraction. The audit counted 105,043,476 numeric records across 22,495 item files. The root example and conversion table did not enter the item corpus. The daily caches, primary cohort and historical-membership comparator were built anew; no existing prepared panel or saved estimate was a fitting input. The separate historical name list and file inventory are declared outcome-free inputs.

The recalculated liquidity cutoff is 36. The full primary cohort contains 597 candidates, 1,580 controls and 27 whole-word key series; the corrected window contains 56,185 observed rows from 585 candidates and 1,559 controls. The primary coefficient is -0.207256905328, with two-way clustered SE 0.027907523169. The historical 43-day comparator remains separate from the corrected 42-day window ending 17 November 2019. Original substring key classification and incomplete-source-file comparators are retained explicitly.

Execution regenerated all 914 historical-date fits per group/model, the frozen-150 references, both simulation families, fresh matched Cloud/Dell paths, centered and uncentered threshold comparisons, uncertainty arrays, empirical response fits, time/missingness/container sensitivities, S1b variants and concentration reconstructions. Numerical figures 4 and S3.1 were redrawn from fresh data; their layout is a replacement, not pixel reproduction.

Twenty-five computational software tests passed. Absorbed estimators were additionally checked against dummy OLS and PanelOLS. A separately written arithmetic checker passed **39,993** checks covering coefficients' recovery counts, Wilson intervals, thresholds, grid crossings, bootstrap results and fresh CSV denominators. The prior 40,011 total included 18 additional copied-file hash checks; those files are now computed afresh, leaving 81 rather than 99 copy-hash checks. No numerical check was removed to obtain agreement. These are same-agent computational checks, not independent human replication.

## Differences and manuscript clarifications

| Topic | v48 | Fresh execution / required clarification |
|---|---|---|
| S1b primary spike total | 25,432 | **20,021** using recovered original logic on the complete snapshot: 1,508 fungible and 18,513 nonfungible. The historical file-set comparator gives 19,800; neither reproduces 25,432. Its provenance remains unresolved. |
| S1b nonfungible rate | 2.75 per 1,000 | Complete snapshot: **2.722499**, rounding to **2.72**. Historical file set: 2.746670, rounding to 2.75. Specify the corpus consistently. |
| Other S1b findings | Fungible 2.21; median spike volume 1; reversion 8.0%; four of five quintiles | Reproduced. The original liquidity-quintile comparison uses **all price levels**, whereas the primary overall rates use mean raw price>10. Clarify this distinction and retain the follow-up missingness caveat. |
| H3 2020 key price |4.81|**4.818232**, rounding to **4.82**, under the stated whole-word/equal-item/equal-day recipe. |
| H3 2023 key price |10.54|**10.567415**, rounding to **10.57**. No settings were changed to recover the retained number. |
| H3 other prices/range |2.03–2.10 in 2017/2018; 9.36 in 2024|Reproduced to stated rounding. Annual ratios are supplied; the 2021 ratio is 4.848553. Clarify the years and rounding behind the stated post-restriction range 4.9–6.7. |
| Concentration price criterion |“Items priced above USD 100”|The reported 22.7% value, about 0.1% units and approximately 1.31b reproduce when **raw records with price > 100** are selected. Selecting whole item histories by mean raw price > 100 instead gives 26.83% value. State the record-level condition. |
| Concentration other claims |Knives 22.1% value/0.24% units;top 100 23.9%;874 items above 1000;>32,000 observations|Reproduced by the declared reconstruction; 37,738 raw price observations exceed1000. Final original concentration code was not authenticated, so this remains a labelled reconstruction. |

H1 reproduces the reported 8.1→2.8 units per100 comparison. Its final-period monthly calculation includes 13 bins, with partial October2019; this is retained, not silently converted to 12 complete months. For H3, historical substring-key prices are different from the corrected 27-key series and remain separately labelled.

The original S1b `np.average` path produces 171,516 all-price spikes; vectorized daily aggregation produces 171,515. One nonfungible observation is on the strict 100% threshold: return 1.0000000000000004 in the original path. The item fails the mean-price>10 filter, so both paths produce the same 20,021 primary count. The affected row is recorded in `S1B_FLOAT_BOUNDARY_DISCREPANCIES.csv`; no epsilon or threshold adjustment was introduced.

## Results/figures not regenerated

Figures 2 and 3 require the verified SteamDB daily peak-player export described by v48. No such export was found in the named project locations or preserved ZIP inventories. Existing images are not that source. Market-only weekly components are supplied, indexed by Sunday week-end (the corresponding Monday is six days earlier); player-normalized values and exact figures are **not regenerated**. No current SteamDB series was substituted.

Figure 1 and the graphical-abstract design are conceptual artwork, not statistical script outputs. Graphical-abstract numerical inputs are regenerated. The unreported planned H1 interrupted-time-series model, H3 general-market comparator, other unreported signature tests and separate forum evidence are outside the executed result set; they are not presented as regenerated. No GamingCrimeData or licensed CrimeBB input was accessed.

The original submitted simulation implementation and seed remain unauthenticated. This release reproduces the final revision specification, not an unknown historical simulation. The exact local Kaggle snapshot is pinned by archive/member hashes; a remote Kaggle version identifier and public release DOI are not established here. Nothing was published.

## Files to review first

1. This report, `RESULT_TO_SCRIPT_MAP.csv`, and `README.md`.
2. `executed_run/comparison/V48_TABLE_COMPARISON.csv` and `V48_PROSE_CLAIM_COMPARISON.csv`.
3. `executed_run/results/PRIMARY_SCENARIO_RESULTS.csv`, `FINAL_RESULTS.csv`, `RECOVERY_CURVES.csv`, and `FIGURE4_DATA.csv`.
4. `executed_run/comparison/S1B_IMPLEMENTATION_COMPARISON.csv` and `executed_run/tables/h3_index_construction_sensitivity.csv`.
5. `executed_run/logs/COMMANDS_raw.json`, `COMMANDS_analysis.json`, `COMMANDS_final.json`, their complete logs, and `local_execution_record` for installation/failure records.

The settings and original code hashes, executed adaptations, input manifest and installation requirements are included. Windows path-length failures were preserved; the successful attempt used a short companion directory and a newly installed environment. The entire raw stage, all analyses and final generation completed with exit 0. Expected v48 results were used only for the separate comparison after execution.

An initial post-execution audit comparison exposed a Windows default-text-encoding error in the comparison reader. Explicit UTF-8 decoding resolved the apparent filename difference; the reference JSON, raw input and analysis were unchanged. The initial comparison and reader version are preserved under `executed_run/comparison/initial_audit_reader/`. Figure-label clarification also preserved the first render and verified that every numerical CSV hash remained unchanged.
