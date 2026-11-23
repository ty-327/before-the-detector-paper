COSE Revision 1 — Emil: analysis plans and timestamps
Reviewer comment R2.1 | Updated 23 November 2026

This separate packet contains the original planning documents, their unchanged
edited public copies, source identities, and the current Appendix A1 mapping.
The verification covers these plan records and their manuscript mapping.

READ
public_copies/ — S1 and S2 documents prepared for public access, with their
README, editorial change record, provenance copy and SHA256SUMS.txt.
originals_for_verification/ — unchanged originals for identity/metadata checks.
current_mapping/Appendix_Table_A1.txt — current manuscript mapping, easy to read.
The CSV contains the same cells. Appendix_A1_source.json records the source
manuscript identities and exact extracted cells.
provenance/PROVENANCE.csv — unchanged source/public-copy hashes and dates.
The matching copy in public_copies/ keeps the public-copy references together.

VERIFY
Extract the ZIP, open its folder, and run:
  python VERIFY_PLANS.py
On Windows, an equivalent command is:
  py -3 VERIFY_PLANS.py
Python 3.8 or later is sufficient; the check uses the standard library locally.
Success returns exit code 0; any failed check returns exit code 1.

A successful check establishes the listed files' hashes/sizes, the four DOCX
files' recorded identities and embedded dates, valid DOCX ZIP/XML, and agreement
between the current mapping CSV and its included source extract. The mapping was
copied from the authorised November 18 manuscript and rechecked against the
delivered clean manuscript, standalone Appendix A and combined Supplementary
Material. All 20 table cells agree. Table A1 and the original plan wording are
unchanged. Appendix_A1_source.json records the current and earlier identities.

RECORDED DATES
S1 original: 17 July 2026, 22:40:01 UTC.
S2 original: 17 July 2026, 22:25:09 UTC.
Both edited public copies: 13 November 2026, 22:30:48 UTC.
Creation and modification fields agree within each of these files.

These fields document embedded metadata. Establishing when the files first
existed, when an analysis first ran and when the plans were publicly registered
requires the corresponding external records. The signature plan records earlier
findings.

OUTSTANDING
Verify the persistent public plan/release URL or DOI, deposited file access and
actual public deposit date, then insert them in the manuscript and reviewer
response to complete the public-access part of R2.1.

verification/TEST_REPORT.txt records clean-extraction and deliberate-error tests.
