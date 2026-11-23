#!/usr/bin/env python3
"""Run or bind a saved-evidence replay, then check the Revision 1 H2 and H3 claims.
Exit 0 is limited to these checks; complete manuscript reproduction remains unestablished.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys

ROOT = Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def verification_interpreter(require_pinned=False):
    """Continue in the environment created by reviewer_test.py --setup."""
    environment = ROOT / ".reviewer_env"
    pinned = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if (environment / "pyvenv.cfg").is_file() and pinned.is_file():
        return str(pinned)
    if require_pinned:
        raise RuntimeError("Setup completed without the required pinned Python environment")
    return sys.executable


def bind_replay(replay, python):
    path = replay / "REVIEW_TEST_RESULT.json"
    receipt = read_json(path)
    required = {"status": "PASS", "mode": "saved_evidence_replay", "summary_rows": 352,
                "recovery_curve_rows": 6608, "fresh_raw_extraction": False,
                "fresh_primary_simulation": False, "fresh_primary_model_fit": False,
                "fresh_H1_H3_reconstruction": False, "source_package_verified_before_and_after": True}
    for key, expected in required.items():
        if receipt.get(key) != expected:
            raise ValueError("Replay receipt failed " + key)
    if not receipt.get("stages") or any(s.get("status") != "PASS" for s in receipt["stages"]):
        raise ValueError("Replay stages did not all pass")
    comparison = receipt.get("reference_comparison", {})
    if comparison.get("passed_table_count") != 10 or comparison.get("failed_table_count") != 0:
        raise ValueError("Replay receipt does not establish ten reference-table matches")
    sources = [p for p in (ROOT / "scripts").rglob("*") if p.is_file() and "__pycache__" not in p.parts]
    sources.append(ROOT / "FINAL_SETTINGS.json")
    sources.append(ROOT / "reviewer_tools/REPLAY_INDEX_RECIPE.json")
    for source in sources:
        candidate = replay / source.relative_to(ROOT)
        if not candidate.is_file() or digest(candidate) != digest(source):
            raise ValueError("Replay script/settings mismatch: " + str(source.relative_to(ROOT)))
    current = subprocess.run(
        [python, str(replay / "scripts/check_results.py"), "--verify-evidence-only"],
        cwd=replay, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1"),
        capture_output=True, text=True)
    if current.returncode:
        raise ValueError("Current replay evidence failed verification: " + current.stderr.strip())
    evidence = json.loads(current.stdout)
    if not (evidence.get("status") == "PASS" and evidence.get("frozen_index_files_verified") == 7
            and evidence.get("arrays_verified") == 42 and evidence.get("strict_hash_files_verified") == 74):
        raise ValueError("Current replay evidence did not establish the required file/array checks")
    return {"status": "PASS", "receipt_sha256": digest(path), "receipt": str(path),
            "basis": "Previously completed saved-evidence run; source/settings and current evidence rechecked now",
            "source_files_matched_now": len(sources),
            "current_evidence_verification": evidence,
            "previous_arithmetic_checks": receipt.get("arithmetic_checks_passed")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--work-dir", type=Path, help="New external replay directory")
    mode.add_argument("--existing-replay", type=Path, help="Bind an already passed replay without repeating it")
    parser.add_argument("--setup", action="store_true", help="Install the exact Python 3.12 environment through reviewer_test.py")
    parser.add_argument("--report-dir", type=Path, help="New external directory for scoped reports")
    args = parser.parse_args()
    if args.existing_replay and args.setup:
        parser.error("--existing-replay cannot be combined with --setup")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
    replay = (args.existing_replay or args.work_dir or ROOT.parent / ("revision1_replay_" + stamp)).resolve()
    out = (args.report_dir or ROOT.parent / ("revision1_check_" + stamp)).resolve()
    if out.exists() or out == ROOT or out.is_relative_to(ROOT):
        parser.error("--report-dir must be new and outside the package")
    if not args.existing_replay and (replay.exists() or replay == ROOT or replay.is_relative_to(ROOT)):
        parser.error("--work-dir must be new and outside the package")
    out.mkdir(parents=True)
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1")
    status = {"execution_mode": "bound_existing_saved_evidence_replay" if args.existing_replay else "new_saved_evidence_replay",
              "reviewer_requested_h2_agreement": "NOT_CHECKED", "corpus_total_25432": "NOT_VERIFIED",
              "historical_h3": "NOT_CHECKED", "full_manuscript_reproduction": "NOT_ESTABLISHED",
              "fresh_primary_model_fit": False, "fresh_H1_H3_reconstruction": False}
    result_path = out / "REVISION1_STATUS.json"
    try:
        def integrity(filename):
            run = subprocess.run([sys.executable, str(ROOT / "verify_release.py"), "--root", str(ROOT)],
                                 env=env, capture_output=True, text=True)
            (out / filename).write_text(run.stdout + run.stderr, encoding="utf-8")
            if run.returncode:
                raise RuntimeError("Package integrity failed: " + filename)
        integrity("package_integrity.log")
        if not args.existing_replay:
            command = [sys.executable, str(ROOT / "reviewer_test.py"), "--work-dir", str(replay)]
            if args.setup:
                command.append("--setup")
            print("Starting saved-evidence replay; no raw-data refit.", flush=True)
            if subprocess.run(command, cwd=ROOT, env=env).returncode:
                raise RuntimeError("Base saved-evidence workflow failed")
        python = verification_interpreter(require_pinned=args.setup)
        status["verification_python"] = python
        status["base_replay"] = bind_replay(replay, python)
        common = ["--manuscript", str(ROOT / "revision1_reference/COSE_Manuscript_Clean_19Nov2026.docx"),
                  "--reviewer-xlsx", str(ROOT / "revision1_reference/COSE_Reviewer_Response_Restart_18Nov2026.xlsx"),
                  "--tables-dir", str(replay / "results"),
                  "--empirical-table", str(replay / "evidence/sources/empirical_response_shapes.csv"),
                  "--key-turnover", str(replay / "evidence/KEY_TURNOVER.json"),
                  "--tables-origin", "saved-evidence-replay"]
        for script, filename in (("validate_revision1.py", "H2_AGREEMENT.json"), ("test_negative_cases.py", "NEGATIVE_TESTS.json")):
            command = [python, str(ROOT / "revision1_validation" / script)] + common + ["--report", str(out / filename)]
            run = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True)
            if run.returncode:
                raise RuntimeError(script + " failed; see " + filename + "; " + run.stderr.strip())
        h2, negatives = read_json(out / "H2_AGREEMENT.json"), read_json(out / "NEGATIVE_TESTS.json")
        if h2.get("reviewer_requested_h2_agreement") != "MATCH" or not negatives.get("all_required_tests_passed"):
            raise RuntimeError("Scoped result receipts did not establish the required checks")
        h3_api = runpy.run_path(str(ROOT / "revision1_comparator/compare_manuscript.py"))
        manuscript = ROOT / "revision1_reference/COSE_Manuscript_Clean_19Nov2026.docx"
        h3_source = ROOT / "reviewer_data/H3_INDEX_CONSTRUCTION.csv"
        h3_targets = h3_api["read_manuscript_h3_targets"](manuscript)
        h3_claims = h3_api["check_h3"](h3_source, h3_targets)
        h3_ok = len(h3_claims) == 10 and all(row["status"] == "PASS" for row in h3_claims)
        h3_report = {"historical_h3": "MATCH_TO_RETAINED_CALCULATION" if h3_ok else "NOT_ESTABLISHED",
                     "manuscript_sha256": digest(manuscript), "evidence_sha256": digest(h3_source),
                     "targets_read_from_docx": h3_targets, "claims": h3_claims,
                     "scope": "H3 displayed values compared with the retained 27-key calculation using the existing rounding rules",
                     "fresh_raw_data_reconstruction": False, "full_manuscript_reproduction": "NOT_ESTABLISHED"}
        (out / "H3_AGREEMENT.json").write_text(json.dumps(h3_report, indent=2) + "\n", encoding="utf-8")
        if not h3_ok:
            raise RuntimeError("H3 manuscript values differ from the retained 27-key calculation; see H3_AGREEMENT.json")
        command = [python, str(ROOT / "reviewer_tools/test_portability_integrity.py"),
                   "--replay", str(replay), "--work-parent", str(out),
                   "--report", str(out / "PORTABILITY_INTEGRITY_TESTS.json")]
        controls = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True)
        (out / "portability_integrity.log").write_text(controls.stdout + controls.stderr, encoding="utf-8")
        portability = read_json(out / "PORTABILITY_INTEGRITY_TESTS.json")
        if controls.returncode or not portability.get("all_required_tests_passed"):
            raise RuntimeError("Current-array/serialization controls failed; see PORTABILITY_INTEGRITY_TESTS.json")
        status.update({"reviewer_requested_h2_agreement": "MATCH", "agreement_components": h2["agreement_components"],
                        "checked_rows": h2["checked_rows"], "negative_tests": "EXPECTED_FAILURES_OBSERVED",
                        "portability_integrity_controls": "PASS",
                        "historical_h3": h3_report["historical_h3"],
                        "manuscript_sha256": digest(ROOT / "revision1_reference/COSE_Manuscript_Clean_19Nov2026.docx"),
                        "reviewer_workbook_sha256": digest(ROOT / "revision1_reference/COSE_Reviewer_Response_Restart_18Nov2026.xlsx")})
        integrity("package_integrity_after.log")
        status["completed_utc"] = datetime.now(timezone.utc).isoformat()
        result_path.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
        print("Reviewer-requested H2: MATCH. Changed-result/missing-file rejections: confirmed.")
        print("H3 displayed values: MATCH_TO_RETAINED_CALCULATION. Corpus: NOT_VERIFIED. Full manuscript: NOT_ESTABLISHED.")
        print("Report: " + str(result_path))
        return 0
    except (Exception, KeyboardInterrupt) as exc:
        status["execution_error"] = str(exc)
        result_path.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
        print("Scoped check failed: " + str(exc) + ". Report: " + str(result_path), file=sys.stderr)
        return 130 if isinstance(exc, KeyboardInterrupt) else 1


if __name__ == "__main__":
    raise SystemExit(main())
