#!/usr/bin/env python3
"""Run the compact COSE reviewer tests and saved-evidence numerical replay.

Examples:
  python reviewer_test.py --setup
  python reviewer_test.py
  python reviewer_test.py --work-dir ../my_reviewer_run
  python reviewer_test.py --verify-only

The source package stays intact. Logs and regenerated results are written to a
new directory outside it. --setup creates .reviewer_env with Python 3.12 and the
exact versions in requirements.txt, then restarts this runner in that environment.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import importlib.metadata
import json
import math
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
import time
import uuid
import zipfile


ROOT = Path(__file__).resolve().parent
EXPECTED_ROWS = 352
EXPECTED_CURVE_ROWS = 6608
SETUP_RECEIPT_ENV = "COSE_REVIEWER_SETUP_RECEIPT"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def work_path(requested: Path | None) -> Path:
    if requested is None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
        requested = ROOT.parent / f"reviewer_run_{stamp}"
    path = requested.expanduser().resolve()
    if path == ROOT or path.is_relative_to(ROOT):
        raise ValueError("The work directory must be outside the source package.")
    if path.exists():
        raise FileExistsError(f"The work directory already exists; choose a new directory: {path}")
    if not path.parent.is_dir():
        raise FileNotFoundError(f"The work directory's parent must already exist: {path.parent}")
    return path


def execution_environment(work: Path) -> dict[str, str]:
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    env.pop("PYTHONOPTIMIZE", None)
    for name in (
        "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS", "BLIS_NUM_THREADS",
    ):
        env[name] = "1"
    env.update({
        "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1",
        "PYTHONDONTWRITEBYTECODE": "1", "MPLCONFIGDIR": str(work / "matplotlib_config"),
        "MPLBACKEND": "Agg",
    })
    return env


def run_logged(name: str, command: list[str], cwd: Path, log_dir: Path,
               env: dict[str, str], stages: list[dict]) -> dict:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{len(stages) + 1:02d}_{name}.log"
    record = {
        "stage": name, "command": command, "cwd": str(cwd),
        "log": str(log_path), "started_utc": utc_now(), "status": "RUNNING",
    }
    stages.append(record)
    print(f"[{len(stages):02d}] {name.replace('_', ' ')} ...", flush=True)
    started = time.monotonic()
    process = None
    try:
        with log_path.open("w", encoding="utf-8") as log:
            log.write("Command: " + json.dumps(command) + "\n\n")
            log.flush()
            process = subprocess.Popen(
                command, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT,
                shell=False,
            )
            while True:
                try:
                    code = process.wait(timeout=30)
                    break
                except subprocess.TimeoutExpired:
                    elapsed = int(time.monotonic() - started)
                    print(f"     {name.replace('_', ' ')} is running ({elapsed}s); log: {log_path.name}", flush=True)
        record["exit_code"] = code
        record["status"] = "PASS" if code == 0 else "FAIL"
        if code != 0:
            raise RuntimeError(f"Stage '{name}' failed with exit code {code}. See {log_path}")
    except BaseException as exc:
        record["status"] = "FAIL"
        record["error"] = str(exc)
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
        raise
    finally:
        record["elapsed_seconds"] = round(time.monotonic() - started, 3)
        record["completed_utc"] = utc_now()
    print(f"     PASS ({record['elapsed_seconds']:.1f}s)", flush=True)
    return record


def exact_dependencies() -> dict[str, str]:
    if sys.version_info[:2] != (3, 12):
        raise RuntimeError("Python 3.12 is required. Run Python 3.12 with --setup to create the pinned environment.")
    if struct.calcsize("P") != 8:
        raise RuntimeError("A 64-bit Python 3.12 interpreter is required for the pinned numerical environment.")
    versions = {}
    failures = []
    for line in (ROOT / "requirements.txt").read_text(encoding="utf-8-sig").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        match = re.fullmatch(r"([A-Za-z0-9][A-Za-z0-9_.-]*)==([^\s;]+)", line)
        if match is None:
            raise ValueError(f"requirements.txt must contain exact package==version pins: {line}")
        package, expected = match.groups()
        try:
            observed = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            observed = "NOT INSTALLED"
        versions[package] = observed
        if observed != expected:
            failures.append(f"{package}: expected {expected}, found {observed}")
    if not versions:
        raise ValueError("requirements.txt contains no pinned dependencies")
    if failures:
        raise RuntimeError("Dependency versions do not match. Run with --setup.\n" + "\n".join(failures))
    return versions


def python312_command() -> list[str]:
    if sys.version_info[:2] == (3, 12):
        return [sys.executable]
    candidates = []
    if os.name == "nt" and shutil.which("py"):
        candidates.append([shutil.which("py"), "-3.12"])
    if shutil.which("python3.12"):
        candidates.append([shutil.which("python3.12")])
    for candidate in candidates:
        result = subprocess.run(
            candidate + ["-c", "import sys; raise SystemExit(sys.version_info[:2] != (3, 12))"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
        )
        if result.returncode == 0:
            return candidate
    raise RuntimeError("Python 3.12 was not found. Install Python 3.12, then run reviewer_test.py --setup.")


def setup_and_restart(args: argparse.Namespace, work: Path) -> int:
    # Setup logs are kept outside the release and moved into the run directory
    # after the restarted runner creates that directory itself.
    setup_dir = Path(tempfile.mkdtemp(prefix="cose_reviewer_setup_", dir=work.parent)).resolve()
    stages: list[dict] = []
    env = execution_environment(work)
    try:
        run_logged("release_preflight_before_setup", [sys.executable, str(ROOT / "verify_release.py"), "--root", str(ROOT)], ROOT, setup_dir, env, stages)
        python = python312_command()
        environment = ROOT / ".reviewer_env"
        interpreter = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        if environment.exists() and not (environment / "pyvenv.cfg").is_file():
            raise RuntimeError(f"Refusing to reuse a directory that is not a virtual environment: {environment}")
        if not environment.exists():
            run_logged("create_pinned_environment", python + ["-m", "venv", str(environment)], ROOT, setup_dir, env, stages)
        if not interpreter.is_file():
            raise RuntimeError(f"Virtual environment interpreter is missing: {interpreter}")
        run_logged("check_environment_python", [str(interpreter), "-c", "import struct,sys; print(sys.version); print('Pointer bits:', struct.calcsize('P') * 8); raise SystemExit(0 if sys.version_info[:2] == (3, 12) and struct.calcsize('P') == 8 else 1)"], ROOT, setup_dir, env, stages)
        run_logged("install_exact_requirements", [str(interpreter), "-m", "pip", "install", "--require-virtualenv", "--only-binary=:all:", "--disable-pip-version-check", "--no-input", "-r", str(ROOT / "requirements.txt")], ROOT, setup_dir, env, stages)
        receipt = setup_dir / "SETUP_RECEIPT.json"
        write_json(receipt, {"status": "PASS", "stages": stages, "environment": str(environment)})
        env[SETUP_RECEIPT_ENV] = str(receipt)
        print("Restarting the reviewer tests in the pinned Python environment.", flush=True)
        # Keep an outer process only to return the restarted runner's exact code.
        return subprocess.run(
            [str(interpreter), str(Path(__file__).resolve()), "--work-dir", str(work)],
            cwd=ROOT, env=env, check=False,
        ).returncode
    except (Exception, KeyboardInterrupt) as exc:
        if not work.exists():
            work.mkdir()
            logs = work / "logs"
            logs.mkdir()
            for stage in stages:
                source = Path(stage["log"])
                if source.is_file():
                    destination = logs / source.name
                    shutil.copy2(source, destination)
                    stage["log"] = str(destination)
            write_json(work / "REVIEW_TEST_RESULT.json", {
                "status": "FAIL", "error": str(exc), "completed_utc": utc_now(),
                "mode": "saved_evidence_replay", "work_dir": str(work), "stages": stages,
                "fresh_raw_extraction": False, "fresh_primary_simulation": False,
                "fresh_H1_H3_reconstruction": False,
            })
        print(f"FAIL: {exc}\nWork directory: {work}", file=sys.stderr, flush=True)
        return 130 if isinstance(exc, KeyboardInterrupt) else 1


def safe_extract(archive_path: Path, work: Path) -> int:
    if not archive_path.is_file():
        raise FileNotFoundError(f"Required evidence archive is missing: {archive_path}")
    with zipfile.ZipFile(archive_path) as archive:
        members = archive.infolist()
        if len(members) > 10000 or sum(item.file_size for item in members) > 1024 ** 3:
            raise ValueError("review_assets.zip exceeds the expected reviewer asset limits")
        seen = set()
        for member in members:
            name = member.filename
            pieces = name.rstrip("/").split("/")
            relative = PurePosixPath(name)
            if ("\\" in name or "\x00" in name or relative.is_absolute()
                    or any(piece in ("", ".", "..") or ":" in piece for piece in pieces)
                    or not pieces or pieces[0] not in {"evidence", "audit", "reference_results"}):
                raise ValueError(f"Unsafe or unexpected asset path: {name}")
            kind = stat.S_IFMT(member.external_attr >> 16)
            if kind not in (0, stat.S_IFREG, stat.S_IFDIR) or member.flag_bits & 1:
                raise ValueError(f"Unsupported asset member: {name}")
            key = str(relative).casefold().rstrip("/")
            if key in seen:
                raise ValueError(f"Duplicate asset path: {name}")
            seen.add(key)
            destination = (work / Path(*relative.parts)).resolve()
            if not destination.is_relative_to(work):
                raise ValueError(f"Asset leaves the work directory: {name}")
        for member in members:
            destination = work / Path(*PurePosixPath(member.filename).parts)
            if member.is_dir():
                destination.mkdir(parents=True, exist_ok=True)
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as source, destination.open("xb") as target:
                    shutil.copyfileobj(source, target)
    return sum(not item.is_dir() for item in members)


def count_csv_rows(path: Path) -> int:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        next(reader)
        return sum(1 for _ in reader)


def require_test_count(record: dict, expected: int) -> int:
    content = Path(record["log"]).read_text(encoding="utf-8", errors="replace")
    matches = re.findall(r"(?m)^Ran (\d+) tests? in ", content)
    if len(matches) != 1 or int(matches[0]) != expected or not re.search(r"(?m)^OK\s*$", content):
        raise RuntimeError(f"{record['stage']} did not report all {expected} tests passing")
    record["tests_passed"] = expected
    return expected


def truthful_replay_metadata(results: Path) -> dict:
    original = results / "GENERATION_STATUS.json"
    producer = json.loads(original.read_text(encoding="utf-8"))
    archived = results / "GENERATION_STATUS_PRODUCER_METADATA.json"
    original.rename(archived)
    scope = {
        "mode": "saved_evidence_replay", "fresh_raw_extraction": False,
        "fresh_primary_simulation": False, "fresh_primary_model_fit": False,
        "fresh_item_classification": False, "fresh_denominator_csv_scan": False,
        "fresh_H1_H3_reconstruction": False,
        "fitted_coefficients": "Retained fitted coefficient arrays from the checked main-code package",
        "random_indices": "Restored from frozen seeds; original array hashes are required and current arrays are checked again by the arithmetic verifier; NPZ container hashes are recorded",
        "denominators": "Compared with retained previously checked totals; the large derived panel is omitted",
        "historical_table_fields": (
            "CSV execution_activity fields are retained historical producer labels for exact reference comparison. "
            "They do not describe the current replay execution."
        ),
        "limitations": [
            "Does not extract or validate the external raw archive.",
            "Does not repeat raw-data classification or primary empirical model fitting.",
            "Does not scan the omitted derived denominator panel.",
            "Does not establish independent human replication or verify scientific interpretation.",
        ],
    }
    current = dict(producer)
    current.update(scope)
    current["primary"] = "Regenerated numerical summaries from retained fitted coefficient evidence"
    current["matched"] = "Regenerated matched comparisons from retained coefficient and calibration evidence"
    current["producer_metadata_file"] = archived.name
    current["metadata_scope_corrected_utc"] = utc_now()
    write_json(original, current)
    write_json(results / "REPLAY_SCOPE.json", scope)
    return scope


def run_review(work: Path) -> int:
    work.mkdir()
    logs = work / "logs"
    logs.mkdir()
    env = execution_environment(work)
    stages: list[dict] = []
    report = {
        "status": "RUNNING", "started_utc": utc_now(), "mode": "saved_evidence_replay",
        "source_package": str(ROOT), "work_dir": str(work), "stages": stages,
        "fresh_raw_extraction": False, "fresh_primary_simulation": False,
        "fresh_primary_model_fit": False, "fresh_denominator_csv_scan": False,
        "fresh_H1_H3_reconstruction": False,
        "environment": {"python": platform.python_version(), "executable": sys.executable,
                        "platform": platform.platform(), "pointer_bits": struct.calcsize("P") * 8,
                        "numerical_threads": 1},
    }
    report_path = work / "REVIEW_TEST_RESULT.json"
    try:
        receipt_path = os.environ.get(SETUP_RECEIPT_ENV)
        if receipt_path:
            receipt = json.loads(Path(receipt_path).read_text(encoding="utf-8"))
            if receipt.get("status") != "PASS":
                raise RuntimeError("The environment setup receipt did not pass")
            for stage in receipt["stages"]:
                source_log = Path(stage["log"])
                destination = logs / source_log.name
                shutil.copy2(source_log, destination)
                stage["log"] = str(destination)
                stages.append(stage)
            report["setup_environment"] = receipt["environment"]
        write_json(report_path, report)
        print(f"Reviewer work directory: {work}", flush=True)
        run_logged("release_preflight", [sys.executable, str(ROOT / "verify_release.py"), "--root", str(ROOT)], ROOT, logs, env, stages)
        report["environment"]["dependencies"] = exact_dependencies()
        print("     Exact dependency versions verified.", flush=True)
        run_logged("dependency_consistency", [sys.executable, "-m", "pip", "check"], work, logs, env, stages)

        for relative in (
            "review_assets.zip", "FINAL_SETTINGS.json", "scripts/generate_results.py",
            "scripts/check_results.py", "scripts/computational_checks.py", "scripts/validate_fe_engine.py",
            "reviewer_tools/restore_replay_indices.py", "reviewer_tools/REPLAY_INDEX_RECIPE.json",
            "reviewer_tools/compare_review_results.py", "launcher_tests/test_start_reproduction.py",
            "start_reproduction.py",
        ):
            if not (ROOT / relative).is_file():
                raise FileNotFoundError(f"Required package file is missing: {relative}")
        report["asset_files_extracted"] = safe_extract(ROOT / "review_assets.zip", work)
        shutil.copytree(ROOT / "scripts", work / "scripts", ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"))
        shutil.copy2(ROOT / "FINAL_SETTINGS.json", work / "FINAL_SETTINGS.json")
        (work / "reviewer_tools").mkdir(exist_ok=True)
        shutil.copy2(ROOT / "reviewer_tools/REPLAY_INDEX_RECIPE.json", work / "reviewer_tools/REPLAY_INDEX_RECIPE.json")
        if (work / "historical/fresh_denominator_panel.csv").exists():
            raise RuntimeError("Compact replay unexpectedly includes the derived denominator panel")
        if not (work / "evidence/INDEPENDENT_DENOMINATORS_CHECKED_LOCAL.json").is_file():
            raise FileNotFoundError("The retained checked denominator summary is missing")

        run_logged("restore_frozen_indices", [sys.executable, str(ROOT / "reviewer_tools/restore_replay_indices.py"), "--root", str(work), "--recipe", str(ROOT / "reviewer_tools/REPLAY_INDEX_RECIPE.json"), "--report", str(work / "INDEX_RESTORE_STATUS.json")], work, logs, env, stages)
        restored = json.loads((work / "INDEX_RESTORE_STATUS.json").read_text(encoding="utf-8"))
        if not (restored.get("status") == "PASS" and restored.get("files_verified") == 7
                and restored.get("arrays_verified") == 42 and restored.get("all_array_hashes_match_original") is True):
            raise RuntimeError("Lossless index reconstruction did not verify all original arrays")
        report["index_reconstruction"] = {key: restored[key] for key in ("files_verified", "arrays_verified", "all_array_hashes_match_original", "all_npz_hashes_match_original")}

        computational = run_logged("computational_checks", [sys.executable, str(work / "scripts/computational_checks.py")], work, logs, env, stages)
        report["computational_tests_passed"] = require_test_count(computational, 25)
        run_logged("fixed_effect_validation", [sys.executable, str(work / "scripts/validate_fe_engine.py")], work, logs, env, stages)
        fixed_effects = json.loads((work / "audit/fe_engine_validation.json").read_text(encoding="utf-8"))
        if (not isinstance(fixed_effects, list) or len(fixed_effects) != 2
                or [item.get("two_way_fixed_effects") for item in fixed_effects] != [False, True]):
            raise RuntimeError("Fixed-effect validation did not report both required model checks")
        for item in fixed_effects:
            error_fields = ["max_coefficient_error", "max_item_covariance_error", "injection_weight_identity_error"]
            if item["two_way_fixed_effects"]:
                error_fields.append("max_two_way_covariance_error")
            if not all(key in item and math.isfinite(float(item[key])) and abs(float(item[key])) < 1e-9 for key in error_fields):
                raise RuntimeError("Fixed-effect validation errors are missing, nonfinite, or exceed tolerance")
        report["fixed_effect_validation"] = fixed_effects
        launcher = run_logged("launcher_tests", [sys.executable, "-m", "unittest", "discover", "-s", str(ROOT / "launcher_tests"), "-p", "test_start_reproduction.py", "-v"], work, logs, env, stages)
        report["launcher_tests_passed"] = require_test_count(launcher, 17)

        results = work / "results"
        run_logged("generate_results", [sys.executable, str(work / "scripts/generate_results.py"), "--out", str(results)], work, logs, env, stages)
        report["scope"] = truthful_replay_metadata(results)
        run_logged("independent_arithmetic_checker", [sys.executable, str(work / "scripts/check_results.py"), "--out", str(results), "--allow-missing-panel"], work, logs, env, stages)
        checker = json.loads((results / "CHECK_STATUS.json").read_text(encoding="utf-8"))
        rows = count_csv_rows(results / "FINAL_RESULTS.csv")
        curve_rows = count_csv_rows(results / "RECOVERY_CURVES.csv")
        if not (checker.get("status") == "PASS" and rows == EXPECTED_ROWS and curve_rows == EXPECTED_CURVE_ROWS
                and checker.get("result_rows") == rows and checker.get("curve_rows") == curve_rows
                and checker.get("fresh_csv_rows_scanned") == 0
                and checker.get("raw_denominator_check_this_execution") is False
                and isinstance(checker.get("checks"), int) and checker["checks"] > 0):
            raise RuntimeError("Checker status, replay row counts, or no-CSV-scan scope did not satisfy the acceptance criteria")
        report.update({"summary_rows": rows, "recovery_curve_rows": curve_rows,
                       "arithmetic_checks_passed": checker["checks"], "checker": checker})

        run_logged("strict_reference_comparison", [sys.executable, str(ROOT / "reviewer_tools/compare_review_results.py"), "--generated", str(results), "--reference", str(work / "reference_results"), "--report", str(work / "REFERENCE_COMPARISON.json")], work, logs, env, stages)
        comparison = json.loads((work / "REFERENCE_COMPARISON.json").read_text(encoding="utf-8"))
        if not (comparison.get("status") == "PASS" and comparison.get("required_table_count") == 10
                and comparison.get("passed_table_count") == 10 and comparison.get("failed_table_count") == 0
                and len(comparison.get("tables", [])) == 10
                and all(table.get("passed") is True for table in comparison["tables"])):
            raise RuntimeError("The strict comparison did not confirm all ten reference tables")
        report["reference_comparison"] = comparison
        run_logged("release_postflight", [sys.executable, str(ROOT / "verify_release.py"), "--root", str(ROOT)], ROOT, logs, env, stages)
        report["status"] = "PASS"
        report["source_package_verified_before_and_after"] = True
        report["completed_utc"] = utc_now()
        write_json(report_path, report)
        print(
            f"\nPASS: {rows} summaries, {curve_rows} recovery-curve rows, "
            f"{checker['checks']} arithmetic checks, and all 10 reference tables.\n"
            f"Saved-evidence replay completed; raw extraction and denominator rescanning were not performed.\n"
            f"Report: {report_path}", flush=True,
        )
        return 0
    except (Exception, KeyboardInterrupt) as exc:
        report.update({"status": "FAIL", "error": str(exc), "completed_utc": utc_now()})
        write_json(report_path, report)
        print(f"\nFAIL: {exc}\nReport: {report_path}", file=sys.stderr, flush=True)
        return 130 if isinstance(exc, KeyboardInterrupt) else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--setup", action="store_true", help="Create/reuse .reviewer_env with Python 3.12, install exact requirements, and run")
    parser.add_argument("--work-dir", type=Path, help="New output directory outside the package; default is a unique sibling directory")
    parser.add_argument("--verify-only", action="store_true", help="Check package file hashes only; do not install dependencies or run tests")
    args = parser.parse_args()
    sys.dont_write_bytecode = True
    if args.verify_only:
        if args.setup or args.work_dir is not None:
            parser.error("--verify-only cannot be combined with --setup or --work-dir")
        env = os.environ.copy()
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["PYTHONUTF8"] = "1"
        return subprocess.run([sys.executable, str(ROOT / "verify_release.py"), "--root", str(ROOT)], cwd=ROOT, env=env, check=False).returncode
    try:
        work = work_path(args.work_dir)
        return setup_and_restart(args, work) if args.setup else run_review(work)
    except (Exception, KeyboardInterrupt) as exc:
        print(f"FAIL: {exc}", file=sys.stderr, flush=True)
        return 130 if isinstance(exc, KeyboardInterrupt) else 1


if __name__ == "__main__":
    raise SystemExit(main())
