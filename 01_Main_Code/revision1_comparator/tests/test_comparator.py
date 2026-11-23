"""Focused validation tests. Corpus fixtures are artificial, never market evidence."""
import argparse
import contextlib
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import compare_manuscript as comparator

_options = argparse.ArgumentParser(add_help=False)
_options.add_argument("--data-dir", type=Path)
_parsed, _remaining = _options.parse_known_args()
DATA_DIR = _parsed.data_dir
sys.argv = [sys.argv[0], *_remaining]


def retained(relative):
    return comparator.evidence_path(ROOT, relative, DATA_DIR)


def mode_args():
    return ["--data-dir", str(DATA_DIR)] if DATA_DIR is not None else []


class ComparatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        (ROOT / "test_work").mkdir(exist_ok=True)
        with (retained("evidence/h3_index_construction.csv")).open(newline="") as handle:
            cls.h3_rows = list(csv.DictReader(handle))
        cls.s1b = comparator.check_s1b(
            retained("evidence/historical_s1b_results.txt"),
            retained("evidence/historical_s1b_spikes.csv"),
            retained("evidence/historical_raw_filenames.json"))

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="synthetic_fixture_", dir=ROOT / "test_work")
        self.folder = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def write_h3(self, rows):
        path = self.folder / "h3.csv"
        with path.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=self.h3_rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
        return path

    def synthetic_corpus_fixture(self, found):
        # This temporary log exists only to test the parser and rejection rules.
        log = self.folder / "SYNTHETIC_UNIT_FIXTURE.txt"
        log.write_text("SECTION 4.1.1 VERIFICATION\n" +
                       f"{'25,432 day-over-day spikes >100%':<44}{found:>22,}\n")
        record = {"definition": comparator.CORPUS_DEFINITION,
                  "source_archive_sha256": comparator.RAW_SHA256,
                  "generator_sha256": comparator.CORPUS_SOURCE_SHA256,
                  "result_log": log.name, "result_log_sha256": comparator.digest(log),
                  "count": found, "test_fixture_only": True}
        path = self.folder / "synthetic_corpus_result.json"
        path.write_text(json.dumps(record))
        return path

    def test_historical_s1b_rate_uses_historical_file_set(self):
        self.assertTrue(all(c["status"] == "PASS" for c in self.s1b))
        rate = next(c for c in self.s1b if c["claim"] == "Historical S1b nonfungible rate per 1,000")
        self.assertAlmostEqual(rate["actual"], 2.7466698580011326, places=12)

    def test_restricted_total_is_never_compared_with_corpus_claim(self):
        row = next(c for c in self.s1b if c["claim"] == "Historical S1b row-count reconciliation")
        self.assertEqual(sum(row["actual"].values()), 19800)
        self.assertNotIn(25432, row["expected"].values())
        self.assertEqual(row["status"], "PASS")

    def test_missing_s1b_detail_cannot_pass_on_summary_alone(self):
        result = comparator.check_s1b(retained("evidence/historical_s1b_results.txt"),
            self.folder / "missing.csv", retained("evidence/historical_raw_filenames.json"))
        self.assertEqual(result[0]["status"], "NOT_VERIFIED")

    def test_corrupt_s1b_report_count_fails_row_reconciliation(self):
        text = comparator.decode_text(retained("evidence/historical_s1b_results.txt"))
        path = self.folder / "bad_summary.txt"
        path.write_text(text.replace("spikes: 18,292", "spikes: 18,293", 1))
        result = comparator.check_s1b(path, retained("evidence/historical_s1b_spikes.csv"),
                                      retained("evidence/historical_raw_filenames.json"))
        self.assertEqual(result[0]["status"], "MISMATCH")

    def test_retained_h3_agrees_with_approved_display_values(self):
        result = comparator.check_h3(retained("evidence/h3_index_construction.csv"))
        self.assertEqual(len(result), 10)
        self.assertTrue(all(c["status"] == "PASS" for c in result))

    def test_actual_manuscript_h3_values_match_the_approved_targets(self):
        manuscript = ROOT.parent / "revision1_reference/COSE_Manuscript_Clean_19Nov2026.docx"
        self.assertEqual(comparator.read_manuscript_h3_targets(manuscript), comparator.H3_TARGETS)

    def test_previous_2020_display_in_manuscript_is_rejected_by_actual_cli(self):
        original = ROOT.parent / "revision1_reference/COSE_Manuscript_Clean_19Nov2026.docx"
        altered = self.folder / "SYNTHETIC_WRONG_2020_DISPLAY.docx"
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        with zipfile.ZipFile(original) as archive:
            document = ET.fromstring(archive.read("word/document.xml"))
            changed = 0
            for paragraph in document.findall(".//w:p", ns):
                if "".join(paragraph.itertext()).startswith("Legacy keys appreciated sharply,"):
                    for node in paragraph.findall(".//w:t", ns):
                        if node.text and "4.82" in node.text:
                            changed += node.text.count("4.82")
                            node.text = node.text.replace("4.82", "4.81")
            self.assertEqual(changed, 1)
            with zipfile.ZipFile(altered, "w") as target:
                for entry in archive.infolist():
                    content = ET.tostring(document, encoding="utf-8", xml_declaration=True) if entry.filename == "word/document.xml" else archive.read(entry.filename)
                    target.writestr(entry, content)
        output = self.folder / "altered_display_report.json"
        executed = subprocess.run([sys.executable, str(ROOT.parent / "compare_manuscript.py"),
                                  *mode_args(), "--manuscript", str(altered), "--report", str(output)],
                                 capture_output=True, text=True)
        self.assertEqual(executed.returncode, 1, executed.stdout + executed.stderr)
        report = json.loads(output.read_text())
        comparison = next(row for row in report["claims"] if row["claim"] == "H3 2020 annual key price")
        self.assertEqual(comparison["status"], "MISMATCH")
        self.assertEqual(comparison["expected"], 4.81)
        self.assertAlmostEqual(comparison["actual"], 4.818231963087509, places=12)
        self.assertFalse(report["manuscript_identity"]["identity_matches_approved"])

    def test_irrelevant_h3_alternatives_do_not_change_comparisons(self):
        rows = [dict(r) for r in self.h3_rows]
        for row in rows:
            if not all(row[k] == v for k, v in comparator.H3_SELECTOR.items()):
                row.update(key_price="123456", ratio="654321", candidate_index="999")
        actual = comparator.check_h3(self.write_h3(rows))
        reference = comparator.check_h3(retained("evidence/h3_index_construction.csv"))
        self.assertEqual(actual, reference)

    def test_corrupt_selected_h3_number_fails_numerical_check(self):
        rows = [dict(r) for r in self.h3_rows]
        for row in rows:
            if row["year"] == "2024" and all(row[k] == v for k, v in comparator.H3_SELECTOR.items()):
                row["key_price"] = "99.36"
        result = comparator.check_h3(self.write_h3(rows))
        target = next(c for c in result if c["claim"] == "H3 2024 annual key price")
        self.assertEqual(target["status"], "MISMATCH")
        self.assertEqual(result[0]["status"], "MISMATCH")

    def test_missing_h3_file_is_not_verified(self):
        self.assertEqual(comparator.check_h3(self.folder / "missing.csv")[0]["status"], "NOT_VERIFIED")

    def test_duplicate_h3_selected_year_is_not_verified(self):
        selected = next(r for r in self.h3_rows if all(r[k] == v for k, v in comparator.H3_SELECTOR.items()))
        result = comparator.check_h3(self.write_h3(self.h3_rows + [selected]))
        self.assertEqual(result[0]["status"], "NOT_VERIFIED")

    def test_missing_corpus_evidence_is_not_verified(self):
        result = comparator.check_corpus(self.folder / "missing.json")
        self.assertEqual(result[0]["status"], "NOT_VERIFIED")
        self.assertIsNone(result[0]["actual"])

    def test_synthetic_parser_reads_found_value_not_claim_label(self):
        result = comparator.check_corpus(self.synthetic_corpus_fixture(999))
        self.assertEqual(result[0]["actual"], 999)
        self.assertEqual(result[0]["status"], "MISMATCH")

    def test_synthetic_matching_corpus_parser_case(self):
        self.assertEqual(comparator.check_corpus(self.synthetic_corpus_fixture(25432))[0]["status"], "PASS")

    def test_s1b_population_cannot_be_relabelled_as_corpus(self):
        path = self.synthetic_corpus_fixture(25432)
        record = json.loads(path.read_text())
        record["definition"]["s1b_category_filter"] = True
        path.write_text(json.dumps(record))
        self.assertEqual(comparator.check_corpus(path)[0]["status"], "NOT_VERIFIED")

    def test_corrupted_corpus_log_hash_is_rejected(self):
        path = self.synthetic_corpus_fixture(25432)
        record = json.loads(path.read_text())
        (path.parent / record["result_log"]).write_text("altered evidence")
        self.assertEqual(comparator.check_corpus(path)[0]["status"], "NOT_VERIFIED")

    def test_changed_retained_evidence_fails_integrity(self):
        path = self.folder / "source.csv"
        path.write_text("original")
        expected = comparator.digest(path)
        (self.folder / "SOURCE_PROVENANCE.json").write_text(json.dumps({"files": [
            {"path": path.name, "bytes": path.stat().st_size, "sha256": expected}]}))
        path.write_text("modified")
        _, check = comparator.check_provenance(self.folder)
        self.assertEqual(check["status"], "MISMATCH")

    def test_current_complete_scope_returns_failure_and_preserves_findings(self):
        output = self.folder / "report.json"
        with contextlib.redirect_stdout(io.StringIO()):
            code = comparator.main([*mode_args(), "--report", str(output)])
        report = json.loads(output.read_text())
        self.assertEqual(code, 1)
        self.assertEqual(report["counts"]["PASS"], 16)
        self.assertEqual(report["counts"]["MISMATCH"], 0)
        self.assertEqual(report["counts"]["NOT_VERIFIED"], 1)
        self.assertEqual(report["full_manuscript_reproduction"], "NOT_ESTABLISHED")

    def test_full_run_cli_is_compatible_and_fails_missing_corpus(self):
        run = self.folder / "run"
        copies = {
            "evidence/h3_index_construction.csv": "tables/h3_index_construction_sensitivity.csv",
            "evidence/historical_s1b_results.txt": "historical/s1b_cache_old_file_set/s1b_results.txt",
            "evidence/historical_s1b_spikes.csv": "historical/s1b_cache_old_file_set/s1b_spikes.csv",
            "evidence/historical_raw_filenames.json": "inputs/historical_raw_filenames.json",
        }
        for source, target in copies.items():
            path = run / target
            path.parent.mkdir(parents=True, exist_ok=True)
            os.link(retained(source), path)
        (run / "inputs/download_manifest.json").write_text(json.dumps(
            {"sha256": comparator.RAW_SHA256, "fresh_extraction": True, "test_fixture_only": True}))
        with contextlib.redirect_stdout(io.StringIO()):
            code = comparator.main(["--run", str(run)])
        self.assertEqual(code, 1)
        self.assertTrue((run / "comparison/V48_PROSE_CLAIM_COMPARISON.csv").is_file())
        report = json.loads((run / "comparison/HISTORICAL_CLAIMS_REPORT.json").read_text())
        self.assertEqual(report["counts"]["MISMATCH"], 0)
        self.assertEqual(report["counts"]["NOT_VERIFIED"], 1)

    def test_separate_ty_data_cli_has_identical_validated_scope(self):
        ty = self.folder / "COSE_Revision1_Ty_Reproducibility_Data"
        for source, target in comparator.TY_DATA_PATHS.items():
            path = ty / target
            path.parent.mkdir(parents=True, exist_ok=True)
            os.link(retained(source), path)
        output = self.folder / "separate_data_report.json"
        with contextlib.redirect_stdout(io.StringIO()):
            code = comparator.main(["--data-dir", str(ty), "--report", str(output)])
        report = json.loads(output.read_text())
        self.assertEqual(code, 1)
        self.assertEqual(report["counts"], {"PASS": 16, "MISMATCH": 0, "NOT_VERIFIED": 1})

    def test_missing_explicit_ty_data_is_not_verified(self):
        output = self.folder / "missing_data_report.json"
        with contextlib.redirect_stdout(io.StringIO()):
            code = comparator.main(["--data-dir", str(self.folder / "missing_ty"), "--report", str(output)])
        report = json.loads(output.read_text())
        self.assertEqual(code, 1)
        self.assertGreater(report["counts"]["NOT_VERIFIED"], 1)


if __name__ == "__main__":
    unittest.main()
