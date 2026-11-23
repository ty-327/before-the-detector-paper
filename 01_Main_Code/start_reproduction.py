#!/usr/bin/env python3
"""Easy-start wrapper for the unchanged COSE reproduction and comparison scripts.

This file contains no estimator, simulation, analytical setting or target result.
Run START_WINDOWS.cmd on Windows, or use --help for the command-line interface.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import struct
import subprocess
import sys
import traceback
import uuid

SOURCE = Path(__file__).resolve().parent


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def choose_archive() -> Path | None:
    """A native file chooser; console fallback when Tk is not installed."""
    root = None
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        selected = filedialog.askopenfilename(
            parent=root,
            title="Select counter-strike-market-sale-data.zip (the raw dataset)",
            initialdir=str(Path.home() / "Downloads"),
            filetypes=[("ZIP archives", "*.zip"), ("All files", "*.*")],
        )
        return Path(selected).resolve() if selected else None
    except (ImportError, RuntimeError, OSError) as exc:
        print("File picker unavailable:", exc)
    except Exception as exc:
        # A missing display or incomplete Tk installation must not prevent CLI use.
        print("File picker unavailable:", exc)
    finally:
        if root is not None:
            root.destroy()
    value = input("Paste the full path to the raw data ZIP (Enter cancels): ").strip().strip('"')
    return Path(value).expanduser().resolve() if value else None


def confirm_start(message: str) -> bool:
    root = None
    try:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        return bool(messagebox.askokcancel("Start COSE reproduction", message, parent=root))
    except Exception:
        print(message)
        return input("Start? Type YES to continue: ").strip().upper() == "YES"
    finally:
        if root is not None:
            root.destroy()


def check_workspace(source: Path, workspace: Path, windows: bool) -> None:
    """Never reuse an earlier run, and never put mutable outputs into the release."""
    source, workspace = source.resolve(), workspace.resolve()
    if workspace.exists():
        raise FileExistsError("Workspace already exists. Choose a new directory; old runs are never overwritten.")
    if workspace.is_relative_to(source):
        raise ValueError("Choose a workspace outside the extracted release folder.")
    if not workspace.parent.is_dir():
        raise FileNotFoundError("The workspace parent does not exist. Choose an existing short parent path.")
    if windows:
        manifest = json.loads((source / "inputs/public_data_manifest.json").read_text(encoding="utf-8"))
        longest = max(len(str(workspace / "run" / Path(e["path"].replace("\\", "/"))))
                      for e in manifest["raw_csv_hashes"])
        if longest >= 240 or len(str(workspace / "env")) > 70:
            raise ValueError(
                "This path is too long for the tested workflow. Extract the release to a short location "
                "such as C:\\cose54, then use START_WINDOWS.cmd again. No files were overwritten."
            )


def command_plan(source: Path, workspace: Path, archive: Path, base_python: str,
                 windows: bool) -> list[tuple[str, list[str]]]:
    """Mirror MAIN_CODE_ACCEPTANCE.txt; argument lists avoid shell quoting problems."""
    vpython = workspace / "env" / ("Scripts/python.exe" if windows else "bin/python")
    py = str(vpython)
    run = str(workspace / "run")
    reference = str(source / "expected_v48")
    steps = [
        ("01_verify_release_and_data", [base_python, "-u", str(source / "verify_release.py"),
                                        "--root", str(source), "--raw", str(archive)]),
        ("02_create_environment", [base_python, "-m", "venv", str(workspace / "env")]),
        ("03_install_pinned_requirements", [py, "-m", "pip", "install", "--require-virtualenv",
                                            "--only-binary=:all:", "-r", str(source / "requirements.txt")]),
        ("04_check_dependencies", [py, "-m", "pip", "check"]),
        ("05_record_installed_versions", [py, "-m", "pip", "freeze", "--all"]),
    ]
    for number, stage in [(6, "raw"), (7, "analysis"), (8, "final")]:
        steps.append((f"{number:02}_{stage}", [py, "-u", str(source / "reproduce.py"),
                     "--archive", str(archive), "--work-dir", run, "--stage", stage]))
    steps.extend([
        ("09_compare_tables", [py, "-u", str(source / "compare_v48.py"),
                                "--run", run, "--reference", reference]),
        ("10_compare_audits", [py, "-u", str(source / "compare_audits.py"),
                                "--run", run, "--reference", reference]),
        ("11_compare_manuscript_history", [py, "-u", str(source / "compare_manuscript.py"), "--run", run]),
        ("12_verify_release_unchanged", [base_python, "-u", str(source / "verify_release.py"),
                                         "--root", str(source)]),
    ])
    return steps


def run_logged(label: str, command: list[str], source: Path, workspace: Path,
               records: list[dict]) -> None:
    """Stream progress to the visible console and save each step's complete log."""
    log = workspace / "launcher_logs" / f"{label}.log"
    env = os.environ.copy()
    env.update(PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1", PYTHONDONTWRITEBYTECODE="1")
    entry = {"step": label, "command": command, "cwd": str(source), "start_utc": utc_now(),
             "log": str(log.relative_to(workspace))}
    records.append(entry)
    write_json(workspace / "LAUNCHER_COMMANDS.json", records)
    print(f"\n=== {label} ===", flush=True)
    print(subprocess.list2cmdline(command), flush=True)
    try:
        with log.open("w", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")
            handle.flush()
            proc = subprocess.Popen(command, cwd=source, env=env, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
            try:
                assert proc.stdout is not None
                for line in proc.stdout:
                    print(line, end="", flush=True)
                    handle.write(line)
                    handle.flush()
                code = proc.wait()
            except BaseException:
                # Ctrl+C is also delivered to same-console child processes on Windows.
                if proc.poll() is None:
                    proc.terminate()
                    try:
                        proc.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait()
                raise
            finally:
                if proc.stdout is not None:
                    proc.stdout.close()
        entry.update(end_utc=utc_now(), exit_code=code)
        if code:
            raise RuntimeError(f"Step {label} stopped with exit {code}. See {log}. "
                               "Keep this run; do not change settings or package versions to force a match.")
    except BaseException as exc:
        entry.setdefault("end_utc", utc_now())
        entry["error"] = str(exc)
        raise
    finally:
        write_json(workspace / "LAUNCHER_COMMANDS.json", records)


def check_comparisons(run: Path) -> dict:
    """A zero process exit alone is insufficient: inspect the comparison verdicts."""
    comparison = run / "comparison"
    table = json.loads((comparison / "COMPARISON_STATUS.json").read_text(encoding="utf-8"))
    audit = json.loads((comparison / "AUDIT_COMPARISON_STATUS.json").read_text(encoding="utf-8"))
    if table.get("status") != "MATCH" or table.get("differing_cells_or_keys") != 0:
        raise RuntimeError("Numerical table comparison reported differences. Retain the reports; do not tune the analysis.")
    if audit.get("status") != "MATCH" or audit.get("differences") != 0:
        raise RuntimeError("Audit comparison reported differences. Retain the reports for Ty's review.")
    with (comparison / "V48_TABLE_COMPARISON.csv").open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    counts = {}
    for filename in ("FINAL_RESULTS.csv", "RECOVERY_CURVES.csv"):
        matches = [r for r in rows if r["table"] == filename and r["field"] == "ROW_KEYS"]
        if len(matches) != 1 or int(matches[0]["different"]) != 0:
            raise RuntimeError(f"Missing or failing row-key comparison: {filename}")
        counts[filename] = int(matches[0]["checked"])
    prose = comparison / "V48_PROSE_CLAIM_COMPARISON.csv"
    if not prose.is_file():
        raise FileNotFoundError("The separate historical-manuscript comparison was not generated.")
    return {"table_comparison": table, "audit_comparison": audit, "matched_rows": counts,
            "prose_comparison": str(prose),
            "scope": "Final numerical and audit comparisons match. Historical v48 prose discrepancies remain for review; "
                     "this does not certify every manuscript statement or regenerate missing SteamDB plots."}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, help="Exact raw Kaggle ZIP; omit to use the file picker")
    parser.add_argument("--workspace", type=Path, help="New, not-yet-existing short workspace outside the release")
    parser.add_argument("--yes", action="store_true", help="Explicitly approve setup/execution without a confirmation dialog")
    parser.add_argument("--dry-run", action="store_true", help="Show commands only: no installation, fitting or writing")
    parser.add_argument("--check-only", action="store_true", help="Verify package and raw-input hashes only; no installation or analysis")
    args = parser.parse_args(argv)
    if args.dry_run and args.check_only:
        parser.error("Choose either --dry-run or --check-only.")
    if not args.dry_run and (sys.version_info[:2] != (3, 12) or struct.calcsize("P") != 8):
        print("Use 64-bit Python 3.12. This launcher will not substitute a different analysis environment.")
        return 2
    if not args.dry_run and os.name != "nt":
        print("This easy-start release targets the recorded Windows execution. Use the original instructions on other platforms.")
        return 2
    archive = args.archive.expanduser().resolve() if args.archive else choose_archive()
    if archive is None:
        print("Cancelled. No run started.")
        return 0
    if not args.dry_run and not archive.is_file():
        raise FileNotFoundError(f"Raw data ZIP not found: {archive}")
    workspace = (args.workspace.expanduser().resolve() if args.workspace else
                 SOURCE.parent / ("cr" + uuid.uuid4().hex[:8]))
    if args.check_only:
        command = [sys.executable, "-u", str(SOURCE / "verify_release.py"),
                   "--root", str(SOURCE), "--raw", str(archive)]
        return subprocess.run(command, cwd=SOURCE, check=False).returncode
    check_workspace(SOURCE, workspace, windows=os.name == "nt")
    plan = command_plan(SOURCE, workspace, archive, sys.executable, windows=os.name == "nt")
    if args.dry_run:
        print("DRY RUN ONLY: no files created, dependencies installed or calculations executed.")
        print("Workspace:", workspace)
        for label, command in plan:
            print(label + ": " + subprocess.list2cmdline(command))
        return 0
    raw_manifest = json.loads((SOURCE / "inputs/public_data_manifest.json").read_text(encoding="utf-8"))
    member_bytes = sum(int(e["bytes"]) for e in raw_manifest["raw_csv_hashes"])
    free_bytes = shutil.disk_usage(workspace.parent).free
    if free_bytes < member_bytes:
        raise OSError("Insufficient free space even for the raw CSV members; caches and results require additional space.")
    message = (
        "This starts the complete recorded analysis, not a demonstration.\n\n"
        f"Raw data: {archive}\nNew workspace: {workspace}\n"
        f"Free disk: {free_bytes / 1024**3:.1f} GiB (not a sufficiency guarantee).\n\n"
        "The launcher verifies hashes, creates an isolated environment, downloads the pinned Python packages, "
        "then runs the unchanged raw, analysis, final and comparison steps.\n\n"
        "Use a suitably resourced research workstation: the retained S1b step uses 16 workers and the complete run "
        "requires substantial memory and disk space. Keep this console open.\n\n"
        "No files are uploaded, and earlier runs, code and scientific settings are not overwritten. Continue?"
    )
    if not args.yes and not confirm_start(message):
        print("Cancelled. No run started.")
        return 0
    # Do not pre-create workspace/run: reproduce.py must initialize it itself.
    workspace.mkdir(exist_ok=False)
    (workspace / "launcher_logs").mkdir()
    records: list[dict] = []
    metadata = {"started_utc": utc_now(), "platform": platform.platform(), "python": sys.version,
                "source": str(SOURCE), "workspace": str(workspace), "raw_archive": str(archive),
                "launcher_sha256": digest(Path(__file__)),
                "package_manifest_sha256": digest(SOURCE / "PACKAGE_MANIFEST.json"),
                "requirements_sha256": digest(SOURCE / "requirements.txt"),
                "scientific_settings_modified": False}
    write_json(workspace / "LAUNCHER_ENVIRONMENT.json", metadata)
    print("Workspace:", workspace, flush=True)
    try:
        for label, command in plan:
            run_logged(label, command, SOURCE, workspace, records)
        result = check_comparisons(workspace / "run")
        result.update(status="NUMERICAL_AND_AUDIT_COMPARISONS_MATCH_WITH_DOCUMENTED_COVERAGE_EXCEPTIONS",
                      finished_utc=utc_now(), work_dir=str(workspace / "run"))
        write_json(workspace / "EASY_START_RESULT.json", result)
        print("\nCOMPLETE: the numerical-table and audit comparisons match.")
        print("Historical v48 prose differences remain in the comparison report; consult the current S3 reconciliation.")
        print("Figures 2-3 are not regenerated: the historical SteamDB input remains missing.")
        print("Send Ty's test note and these logs/reports back to Stephen:", workspace)
        return 0
    except BaseException as exc:
        failure = {"status": "STOPPED_REVIEW_REQUIRED", "finished_utc": utc_now(),
                   "error": str(exc) or type(exc).__name__, "workspace": str(workspace)}
        write_json(workspace / "EASY_START_RESULT.json", failure)
        (workspace / "launcher_logs/STOPPED.txt").write_text(traceback.format_exc(), encoding="utf-8")
        print("\nSTOPPED. The attempt and logs are preserved:", workspace)
        print(str(exc) or type(exc).__name__)
        return 130 if isinstance(exc, KeyboardInterrupt) else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print("\nUnable to start:", exc)
        raise SystemExit(1)
