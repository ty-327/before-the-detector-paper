#!/usr/bin/env python3
"""Test evidence portability and rejection controls on disposable replay copies."""
from __future__ import annotations

import argparse
import csv
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

import numpy as np

PACKAGE = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@contextmanager
def preserve(path):
    saved = path.read_bytes()
    try:
        yield
    finally:
        path.write_bytes(saved)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replay", type=Path, required=True, help="A completed saved-evidence replay")
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--work-parent", type=Path, help="Parent for a temporary copy; defaults to the replay's parent")
    args = parser.parse_args()
    replay = args.replay.resolve()
    report_path = args.report.resolve()
    result = {"status": "RUNNING", "reviewer_comment": "R2.2", "cases": [],
              "scope": "Verification controls on copies of a completed saved-evidence replay; no scientific refit",
              "fresh_raw_extraction": False, "fresh_primary_model_fit": False,
              "all_required_tests_passed": False}
    try:
        receipt = json.loads((replay / "REVIEW_TEST_RESULT.json").read_text(encoding="utf-8"))
        if receipt.get("status") != "PASS" or receipt.get("mode") != "saved_evidence_replay":
            raise ValueError("A completed, passed saved-evidence replay is required")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        parent = (args.work_parent or replay.parent).resolve()
        if parent == PACKAGE or parent.is_relative_to(PACKAGE):
            raise ValueError("Test working files must be outside the source package")
        with tempfile.TemporaryDirectory(prefix="portability_controls_", dir=parent) as temporary:
            root = Path(temporary) / "replay"
            root.mkdir()
            for name in ("scripts", "evidence", "audit", "reviewer_tools", "results"):
                shutil.copytree(replay / name, root / name, ignore=shutil.ignore_patterns("__pycache__"))
            for name in ("FINAL_SETTINGS.json", "INDEX_RESTORE_STATUS.json"):
                shutil.copy2(replay / name, root / name)
            command = [sys.executable, str(root / "scripts/check_results.py"), "--verify-evidence-only"]
            env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1")

            def run_case(name, expected_error=None, cmd=None, details=None):
                completed = subprocess.run(cmd or command, cwd=root, env=env, capture_output=True, text=True)
                passed = completed.returncode == 0 if expected_error is None else (
                    completed.returncode != 0 and expected_error in completed.stderr)
                case = {"case": name, "expected": "PASS" if expected_error is None else "REJECT",
                        "exit_code": completed.returncode, "test_passed": passed}
                if expected_error:
                    case["required_error"] = expected_error
                    case["observed_error"] = completed.stderr.splitlines()[-1] if completed.stderr else ""
                else:
                    verified = json.loads(completed.stdout) if completed.returncode == 0 else {}
                    passed = passed and verified.get("status") == "PASS" and verified.get("arrays_verified") == 42
                    case["test_passed"] = passed
                    case["files_verified"] = verified.get("files_verified")
                    case["arrays_verified"] = verified.get("arrays_verified")
                    case["different_npz_containers"] = sum(not row["original_container_match"]
                                                           for row in verified.get("files", []))
                if details:
                    case.update(details)
                result["cases"].append(case)
                if not passed:
                    raise AssertionError("Control failed: " + name + "\n" + completed.stdout[:400] + completed.stderr[-2000:])
                return case

            run_case("unchanged_current_evidence")
            recipe_path = root / "reviewer_tools/REPLAY_INDEX_RECIPE.json"
            recipe = json.loads(recipe_path.read_text(encoding="utf-8"))
            entry = recipe["files"][0]
            target = root / entry["path"]
            with np.load(target, allow_pickle=False) as archive:
                arrays = {name: archive[name] for name in archive.files}

            with preserve(target):
                before = digest(target)
                np.savez(target, **arrays)
                if digest(target) == before:
                    raise AssertionError("Alternative serialization did not change the container")
                case = run_case("same_arrays_different_npz_serialization", details={
                    "method": "numpy.savez / ZIP_STORED; all original arrays unchanged",
                    "before_sha256": before, "after_sha256": digest(target)})
                if case["different_npz_containers"] != 1:
                    raise AssertionError("The alternative container was not identified")

            with preserve(target):
                altered = {name: array.copy() for name, array in arrays.items()}
                old = int(altered["noise_indices"][0])
                altered["noise_indices"][0] = (old + 1) % entry["frozen_rows"]
                np.savez_compressed(target, **altered)
                stale = root / "INDEX_RESTORE_STATUS.json"
                before_receipt = digest(stale)
                full_checker = [sys.executable, str(root / "scripts/check_results.py"),
                                "--out", str(root / "results"), "--allow-missing-panel"]
                run_case("post_generation_noise_change_with_stale_pass_receipt",
                         "Current frozen-array verification failed: " + entry["path"] + ":noise_indices",
                         cmd=full_checker, details={"old_value": old, "new_value": int(altered["noise_indices"][0]),
                                                   "mutation_timing": "After completed restoration and result generation"})
                if digest(stale) != before_receipt:
                    raise AssertionError("The checker changed the prior restoration receipt")
                restore = [sys.executable, str(PACKAGE / "reviewer_tools/restore_replay_indices.py"),
                           "--root", str(root), "--recipe", str(PACKAGE / "reviewer_tools/REPLAY_INDEX_RECIPE.json")]
                run_case("restore_rejects_preexisting_changed_array", "Original-array verification failed: "
                         + entry["path"] + ":noise_indices", cmd=restore)

            with preserve(target):
                altered = {name: array.copy() for name, array in arrays.items()}
                altered["bootstrap_run_indices"][0, 0] = (
                    int(altered["bootstrap_run_indices"][0, 0]) + 1) % recipe["settings"]["repetitions"]
                np.savez_compressed(target, **altered)
                run_case("current_bootstrap_index_change", "Current frozen-array verification failed: "
                         + entry["path"] + ":bootstrap_run_indices")

            other = root / "evidence/sources/date_calibration_full_calendar.csv"
            with preserve(other):
                with other.open(encoding="utf-8-sig", newline="") as stream:
                    reader = csv.DictReader(stream)
                    columns, values = reader.fieldnames, list(reader)
                values[0]["coefficient"] = str(float(values[0]["coefficient"]) + 0.001)
                with other.open("w", encoding="utf-8", newline="") as stream:
                    writer = csv.DictWriter(stream, fieldnames=columns)
                    writer.writeheader()
                    writer.writerows(values)
                run_case("unrelated_evidence_change", "Current evidence SHA-256 mismatch: evidence/sources/date_calibration_full_calendar.csv")

            with preserve(recipe_path):
                recipe_path.write_bytes(recipe_path.read_bytes() + b"\n")
                run_case("changed_frozen_recipe", "Frozen index recipe SHA-256 mismatch")

            manifest_path = root / "audit/REUSED_FILE_MANIFEST.json"
            with preserve(manifest_path):
                decoy = root / "evidence/undeclared_randomness.npz"
                decoy.write_bytes(b"not original evidence")
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                manifest.append({"evidence": "evidence/undeclared_randomness.npz", "sha256": "0" * 64})
                manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
                run_case("undeclared_randomness_filename_has_no_exemption",
                         "Current evidence SHA-256 mismatch: evidence/undeclared_randomness.npz")

        result.update(status="PASS", all_required_tests_passed=True,
                      completed_utc=datetime.now(timezone.utc).isoformat(),
                      source_replay_receipt_sha256=digest(replay / "REVIEW_TEST_RESULT.json"))
    except Exception as exc:
        result.update(status="FAIL", error=str(exc), completed_utc=datetime.now(timezone.utc).isoformat())
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["all_required_tests_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
