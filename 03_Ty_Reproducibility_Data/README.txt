COSE Revision 1 — Ty: reproducibility data
H3 values aligned with the retained 27-key calculation
Updated 20 November 2026

This separate derived-data packet supports R2.2 and the retained H2 additions for
R1.1–R1.4 and R2.4–R2.5. It preserves the numerical records and their provenance.
The four approved H3 entries now agree with the retained 27-key calculation.

DATA
data/ITEM_CLASSIFICATIONS.csv: all 22,495 item records and eligibility fields.
data/container_definitions.csv: 597 candidate rows, including 29 key-dependent
container exclusion flags. It also preserves the source's broader-container flag.
data/randomization_dates_frozen.csv: 150 revision-stage calibration dates.

data/H2/: 32 profile summaries, 640 recovery-curve rows, 14 estimable empirical
specifications, two baseline/denominator rows and two calibration rows. The
abrupt-step summary rows supply Table A2; the eight profiles supply Table A3.
Scope: full archive, item/date effects, all candidates or 29-container exclusion,
neutral or observed background, eventual amplitude and centred 150-date
calibration. The 28-day delay has no estimable within-window coefficient.
settings/: unchanged recorded settings. Their original broader scope is retained.

data/H3/INDEX_CONSTRUCTION_27KEYS.csv: actual 2017–2024 annual records for the
27 whole-word keys and equal-item/equal-day recipe. Within-item daily prices use
recorded quantities. Available item prices are averaged by day, then observed
days are averaged by year. Missing prices remain missing.

H3 DISPLAY AGREEMENT
The manuscript now reports 4.82 and 10.57 for the 2020 and 2023 key prices,
5.4–5.6 for the 2017–2018 ratio range and 4.8–6.7 for 2020–2024. These are the
ordinary rounded displays of the retained 27-key calculation. The annual
records, index recipe and source 64-row method-comparison table are unchanged.
provenance/H3_DISPLAY_ALIGNMENT.json records the four corrections and the
current clean reading revision.

data/S1b/: unchanged historical spike records and the 22,420-name source inventory.
The primary classified sample has 1,508 fungible and 18,292 nonfungible spikes.
The original result record gives 6,659,701 nonfungible item-days: its rate rounds
to 2.75 per 1,000. These are historical classified-sample results. Their 19,800
combined spikes concern the classified sample. The distinct corpus-wide count
of 25,432 awaits its original result log. The original corpus-method script is
retained. The scripts/results under provenance document the historical methods;
current execution commands appear below.

VERIFY
Extract the ZIP, open its folder, and run: python VERIFY_DATA.py
On Windows: py -3 VERIFY_DATA.py
Python 3.8 or later; the check uses the standard library locally.
Exit 0 means the package hashes, CSV types/counts and declared dataset scopes
agree. Exit 1 means an integrity/structure check failed.
verification/TEST_REPORT.txt records testing.

EXECUTION AND ACCESS
This packet provides retained data for verification. SOURCE_RECORDS.json gives
the copy/projection provenance; DATA_SCHEMA.json preserves types and missingness.
Source evidence-path columns identify historical run files. The companion main
code supplies the executable workflow and retained coefficient evidence.

Companion main code in this submission package: ../01_Main_Code/.
The code and data folders remain side by side under 04_Code_and_Data. From
../01_Main_Code/, compare the retained historical claims with:
  python compare_manuscript.py --data-dir "../03_Ty_Reproducibility_Data" --report "../historical_claims_report.json"
The comparison checks the corrected H3 entries with the other retained claims.
The report gives 16 agreements and one corpus claim awaiting evidence, with
exit 1 recording that outstanding source requirement.
Bundled main code: COSE_Revision1_Submission_Package_20Nov2026.zip,
04_Code_and_Data/01_Main_Code/. Its verification covers saved-evidence replay
and the requested Revision 1 H2 results, with a separate retained H3 comparison.
Full reconstruction requires the external Kaggle archive, original H3 item-day
panel, original SteamDB player-count input and original computational records.
See ../../06_Verification/VERIFICATION_REPORT.txt for the completed checks and
remaining source and public-access requirements.
Verified public repository URL or DOI: NOT YET SUPPLIED.
Use DATA_STATUS.json for the current manuscript identities and verification scope.
