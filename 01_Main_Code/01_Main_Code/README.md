# COSE Revision 1 main code

**This package verifies the reviewer-requested H2 results and corrected H3 values against the current Revision 1 manuscript.** It regenerates summaries from retained coefficient evidence and checks the H3 displays against the retained 27-key calculation.

Estimation algorithms, settings, seeds, frozen lists and saved scientific evidence are preserved. Verification under reviewer comment R2.2 accommodates equivalent NPZ serialization while checking every current random-index array against the frozen recipe. The reference manuscript and 15-comment reviewer spreadsheet include the four approved H3 corrections and the author's clean reading revision. Emil's timestamps and Ty's reproducibility data remain separate packets.

## Run the current checks

Extract the ZIP and use **64-bit Python 3.12**. On Windows, double-click `START_REVISION1_WINDOWS.cmd`. On macOS/Linux:

```bash
python3.12 run_revision1.py --setup
```

The first run installs exact dependencies, runs the saved-evidence reviewer workflow, and checks the current H2 claims, H3 displayed values, changed-result/missing-file rejections, and portability/integrity controls. All checks after setup use the created pinned Python environment, even when the launching Python has no NumPy installed. Read `REVISION1_STATUS.json` in the printed external report folder. To select new folders, use `--work-dir` and `--report-dir`.

To bind an already passed replay from this release without repeating its result arithmetic:

```bash
python run_revision1.py --existing-replay "/path/to/passed_reviewer_run"
```

This checks the previous receipt, current scripts/settings and current evidence files, then compares the supplied results with the actual current manuscript. It verifies the arrays themselves and records `bound_existing_saved_evidence_replay`. Exit 0 confirms the checks described below.

## What a successful run establishes

The base workflow checks dependencies, computational/fixed-effects calculations and 10 reference tables. It regenerates 352 summary and 6,608 recovery rows from saved coefficient evidence.

The H2 validator checks two baseline groups, 14 retained empirical profile fits, 32 requested scenarios and 640 recovery rows against the actual DOCX's H2 statement and Tables A2–A3. It derives probabilities, Wilson intervals, qualifying doses, percentage changes and turnover ratios. Retained empirical fits are labelled separately from regenerated summaries. A changed beta, changed floor and missing table must each fail.

The H3 check reads the price and ratio values directly from the delivered clean DOCX and compares them with the unchanged 27-key calculation. It uses the existing ordinary display rounding. H2 source-identity checks bind the entire manuscript and reviewer spreadsheet to their approved hashes. A separate negative control returns 4.82 to 4.81 in a disposable manuscript and requires an H3 numerical mismatch.

The verifier checks the current contents of exactly seven reconstructed NPZ files: all 42 arrays must retain their names/order, shapes, dtypes and original raw-byte SHA-256 hashes. The frozen recipe itself has a pinned SHA-256. The other 74 evidence files retain strict original-file hash checks. A previous PASS receipt cannot exempt changed evidence.

The additional controls accept identical arrays stored in a different NPZ container and reject a post-generation random-draw change, a changed bootstrap index, unrelated changed evidence, a modified recipe and an undeclared filename ending in `_randomness.npz`. They also confirm that restoration rejects a pre-existing changed array. These verification tests use disposable copies and preserve the statistical analysis.

Current receipts are in `proof/current/`; earlier receipts are preserved in the labelled historical folders. Detailed H2 scope/tolerances are in `revision1_validation/README.txt`. `PACKAGE_MANIFEST.json` covers every delivered file except itself. `provenance/REVISION1_SOURCE_PRESERVATION.json` records the current document identities and preserved scientific sources. `provenance/CODE_CHANGE_LOG.csv` records the preceding verification changes.

To rerun just the portability/integrity controls after a passed replay:

```bash
python reviewer_tools/test_portability_integrity.py --replay "/path/to/passed_reviewer_run" --report "portability_tests.json"
```

The recorded execution used Linux, Python 3.12 and stock zlib. Alternate valid NPZ serialization was tested. Native Windows/macOS and zlib-ng execution were not tested.

## Historical comparison with Ty's separate data

Ty's separate dataset is the sibling folder `03_Ty_Reproducibility_Data`. From this main-code folder, run:

```bash
python compare_manuscript.py --data-dir "../03_Ty_Reproducibility_Data" --report "../historical_claims_report.json"
```

The current expected result is **16 PASS, 0 MISMATCH and 1 corpus NOT_VERIFIED**, exit 1. H3 values agree with the retained calculation. The corpus-wide claim awaits its original result evidence, which accounts for the nonzero exit status. Ty's packet contains the large historical S1b file; this package contains the comparison code, source methods and provenance.

For a full raw-data run, use `python compare_manuscript.py --run "/path/to/full_run"`. Its report is written under that run's `comparison` folder. The comparator reads the bundled clean manuscript by default; `--manuscript` can identify another clean DOCX, whose identity and printed H3 values are checked. An actual corpus-wide record can be supplied with `--corpus-result`; selected-arm counts cannot replace the corpus total.

## Inputs for full reconstruction

The completed Dell raw-data execution reproduced the reported H1 comparison of 8.1 to 2.8 sales per 100 candidate sales and the revised 35%/50% calibration. It matched 352 result summaries and 6,608 recovery-curve rows. The compact package verification checks the retained evidence and its agreement with the current manuscript. These completed analyses do not need another raw-data run.

The full raw-data route remains `reproduce.py`, with `START_WINDOWS.cmd` as its separate launcher. It uses the external Kaggle archive identified in `inputs/public_data_manifest.json` and `REPRODUCTION_SPECIFICATION.json`: 901,195,556 bytes, SHA256 `e00557bd8dc6d5e1a09f8da36213039ac23950f9613e245db49c6ef564ce6df7`. Dataset: https://www.kaggle.com/datasets/kieranpoc/counter-strike-market-sale-data

The recorded exceptions concern the historical SteamDB export for Figures 2–3, supporting output for the corpus-wide 25,432 count, and authentication of the original submission-era simulation implementation, seed and draw list. The supplied dates document the completed revision-stage calibration. The original planned H1 interrupted-time-series model was outside the executed result set; the reported H1 comparison was reproduced. Public access also requires a stable archive URL and the actual plan deposit date. These specific exceptions explain the machine-readable full-manuscript status `NOT_ESTABLISHED`.
