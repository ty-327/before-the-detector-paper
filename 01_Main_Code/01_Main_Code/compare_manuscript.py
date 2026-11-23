#!/usr/bin/env python3
"""Strict historical comparison with explicit external data. The approved H3
values agree with retained evidence; the unverified corpus total returns nonzero.
"""
import argparse
import os
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--run", type=Path, help="Full raw-data run outputs")
    source.add_argument("--data-dir", type=Path, help="Extracted COSE_Revision1_Ty_Reproducibility_Data folder")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--corpus-result", type=Path)
    parser.add_argument("--manuscript", type=Path, help="Clean manuscript to check; defaults to the approved bundled DOCX")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    report = args.report or (args.run / "comparison/HISTORICAL_CLAIMS_REPORT.json" if args.run else root.parent / "COSE_Revision1_Validation_Results/HISTORICAL_CLAIMS_REPORT.json")
    command = [sys.executable, str(root / "revision1_comparator/compare_manuscript.py"),
               "--run" if args.run else "--data-dir", str(args.run or args.data_dir), "--report", str(report)]
    if args.corpus_result:
        command += ["--corpus-result", str(args.corpus_result)]
    if args.manuscript:
        command += ["--manuscript", str(args.manuscript)]
    return subprocess.run(command, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1")).returncode


if __name__ == "__main__":
    raise SystemExit(main())
