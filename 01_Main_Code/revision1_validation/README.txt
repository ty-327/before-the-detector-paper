REVISION 1 H2 CLAIM VALIDATOR

Requires Python 3.9 or later; standard library only. Input files are read only.

Run:
  python validate_revision1.py --manuscript MANUSCRIPT.docx --reviewer-xlsx REVIEWER.xlsx --tables-dir RESULTS --key-turnover KEY_TURNOVER.json --report agreement.json

RESULTS must contain BASELINES_AND_DENOMINATORS.csv,
PRIMARY_SCENARIO_RESULTS.csv, EMPIRICAL_RESPONSE_SPECIFICATIONS.csv and
RECOVERY_CURVES.csv. Use retained v56 tables or compatible replay outputs.
The default revision1_targets.json is anchored to the actual November 18
reviewer spreadsheet and its accepted-view November 19 clean manuscript.
The XLSX is identified by its verified source hash; no spreadsheet library is
needed. The actual current DOCX is read, including Appendix Tables A.2 and A.3.

Exit 0 / reviewer_requested_h2_agreement=MATCH means these retained inputs
agree with the specified H2 claims, using the documented numerical tolerances.
Exit 1 means a required input, source identity or numerical check failed.
full_manuscript_reproduction is always NOT_ESTABLISHED.

When replay outputs do not emit empirical profile fits, add:
  --empirical-table RETAINED_EMPIRICAL_RESPONSE_SPECIFICATIONS.csv --tables-origin saved-evidence-replay
This reads the retained fit file directly, records its path and SHA256, and
labels it separately from the supplied replay summary tables. No file is copied
into the replay results. The replay-origin label is user supplied; the validator
does not itself execute or authenticate the preceding replay process.

The validator derives recovery probabilities and 95% Wilson intervals from
counts, first tested doses reaching 80% recovery, adjacent doses, exp(beta)-1
changes and key/candidate turnover ratios. It checks 32 requested scenarios,
640 recovery rows, 14 empirical profile rows, Tables A.2/A.3 and the main H2
statement. Empirical coefficients/SEs/CIs and conditional resampling ranges
are compared with retained results; models, simulations and bootstrap draws
are not rerun. Extra profiles and calibrations are outside this target.

Full-precision comparisons use absolute tolerance 1e-10 and relative 1e-9.
Published four-decimal coefficients use half-unit rounding tolerance 0.000050001;
two-decimal percentages use 0.005000001 percentage points. Grid doses, unit
totals and document identities are checked separately.

Run the control and rejection tests with the same input arguments:
  python test_negative_cases.py --manuscript MANUSCRIPT.docx --reviewer-xlsx REVIEWER.xlsx --tables-dir RESULTS --key-turnover KEY_TURNOVER.json --report negative_tests.json

These tests alter a beta, alter a floor and remove a required table in temporary
copies. Each must return exit 1 for the expected reason. The originals are not
changed.

This validator does not certify historical H1/H3/S1b results, original
item-effects/calibration results, source-data correctness, missing SteamDB
inputs, public repository access or the actual plan deposit date. Its MATCH
result must not be described as full-manuscript reproduction.
