REVISION 1 HISTORICAL CLAIMS COMPARATOR

This checks the retained historical evidence against the current Revision 1.
The comparison targets include the four author-approved H3 display corrections.
Models, covariance estimators, data transformations and retained results remain
unchanged.

Run the retained-evidence comparison:
  python compare_manuscript.py

Compare an existing full raw-data run (previous CLI retained):
  python compare_manuscript.py --run /path/to/full_run

Use the separately supplied Ty data packet:
  python compare_manuscript.py --data-dir /path/to/COSE_Revision1_Ty_Reproducibility_Data

Run focused verification tests:
  python -m unittest discover -s tests -v

With separately delivered Ty data:
  python tests/test_comparator.py --data-dir /path/to/COSE_Revision1_Ty_Reproducibility_Data -v

Python standard library only. A nonzero comparison exit is expected for the
current evidence: the corpus-wide spike count has no verified result file.
All 16 supported comparisons, including the corrected H3 values, pass. S1b's historical-file-set
rate and supporting counts agree. Test-suite success means the checker correctly
accepts supported comparisons and rejects incorrect or missing evidence; it
does not mean all manuscript claims have been verified.

CORRECTED DEFINITIONS

The manuscript's 25,432 is a corpus-wide count. The recovered corpus generator
reads all nonempty item histories with full-sample mean price above USD 10 and
at least two observed daily prices. It has no S1b category or 30-day filter.
The old comparator incorrectly compared that claim with the sum of S1b's two
restricted arms. That comparison has been removed.

The historical S1b file set contains 22,420 named source files. Its retained
outputs have 1,508 fungible and 18,292 nonfungible primary spikes; rates are
2.2091645168 and 2.7466698580 per 1,000 item-days. The latter rounds to 2.75.
The restricted total, 19,800, is not an alternative corpus count.

H3 checks use only full_zip / whole_word_27keys /
equal_item_daily_mean_then_equal_days. Alternative key groups and weightings
are not tested against the manuscript and cannot substitute for this recipe.
Prices use ordinary two-decimal display; ratios use one decimal. The same
rounding and tolerances are retained. H3 targets are read directly from the
bundled clean DOCX, and its SHA-256 is checked against SOURCE_PROVENANCE.json.
Use --manuscript PATH to check a supplied clean DOCX. A changed printed value
produces a numerical mismatch as well as an identity mismatch.

ACTUAL CORPUS RESULT REQUIRED

An optional --corpus-result JSON, or full_run/tables/corpus_spike_result.json,
must supply the definition exactly recorded in compare_manuscript.py's
CORPUS_DEFINITION, source_archive_sha256, generator_sha256, count, a relative
result_log filename, and result_log_sha256. The log must be an actual retained
output of the recovered corpus generator. The checker reads the FOUND value,
not the historical 25,432 CLAIM label printed by that generator. No result file
is supplied because the corpus output has not been recovered. Do not create a
record containing the desired count in place of execution evidence.

SOURCE AND SCOPE

SOURCE_PROVENANCE.json identifies the current manuscript and every unchanged
retained source by archive, member, byte count and SHA-256. Source methods are
provided for inspection and are not run by this comparator. The two S1b files
are retained November 12 reconstructions of historical logic, not a claim that
the original submission's execution files were recovered.

The full-run CLI writes HISTORICAL_CLAIMS_REPORT.json and
REVISION1_CLAIM_COMPARISON.csv. It also writes the latter under the old
V48_PROSE_CLAIM_COMPARISON.csv filename solely for launcher compatibility; the
contents and exit status use the corrected Revision 1 definitions.

H2 and the requested Appendix A checks are separate. Their successful replay
does not turn this historical-claims result into a full-manuscript PASS.
The raw corpus and missing SteamDB source are not included. No raw model,
full primary simulation or new research analysis is performed here.

INTEGRATION

Preserve this folder as revision1_comparator in the main-code package.
For separate delivery, retain compare_manuscript.py, SOURCE_PROVENANCE.json,
source_methods/ and this README in the main code; the evidence/ files may remain
solely in Ty's data packet. In that layout require explicit --data-dir or --run.
--data-dir reads Ty's data/S1b/historical_spikes.csv,
data/S1b/historical_raw_filenames.json, provenance/historical_S1b_results.txt,
and provenance/H3_INDEX_CONSTRUCTION_source.csv, validating their original hashes.
The full-run mode checks the corresponding existing run outputs numerically,
without requiring them to have retained files' byte serialization.
Replace the active root compare_manuscript.py with a small runpy wrapper that
executes revision1_comparator/compare_manuscript.py as __main__. Existing --run
arguments will be forwarded. Do not keep the old false comparator active.
The H3 correction is complete; corpus evidence and public archive identifiers
remain separate requirements.
