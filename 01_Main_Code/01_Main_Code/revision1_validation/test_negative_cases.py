#!/usr/bin/env python3
"""Run the validator control and three required rejection tests on temporary copies."""
import argparse
import csv
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

FILES = ("BASELINES_AND_DENOMINATORS.csv", "PRIMARY_SCENARIO_RESULTS.csv",
         "EMPIRICAL_RESPONSE_SPECIFICATIONS.csv", "RECOVERY_CURVES.csv")


def change_row(path, selector, field, change):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        fields, rows = reader.fieldnames, list(reader)
    matches = [row for row in rows if selector(row)]
    if len(matches) != 1:
        raise RuntimeError("Mutation did not identify exactly one row")
    matches[0][field] = change(matches[0][field])
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("manuscript", "reviewer-xlsx", "tables-dir", "key-turnover"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--empirical-table", type=Path)
    parser.add_argument("--tables-origin", choices=("retained", "saved-evidence-replay"), default="retained")
    parser.add_argument("--targets", type=Path, default=Path(__file__).with_name("revision1_targets.json"))
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    command = [sys.executable, str(Path(__file__).with_name("validate_revision1.py")),
               "--manuscript", str(args.manuscript), "--reviewer-xlsx", str(args.reviewer_xlsx),
               "--key-turnover", str(args.key_turnover), "--targets", str(args.targets),
               "--tables-origin", args.tables_origin]

    def run(tables, empirical=None):
        extra = ["--empirical-table", str(empirical)] if empirical else []
        process = subprocess.run(command + ["--tables-dir", str(tables)] + extra,
                                 capture_output=True, text=True, timeout=60)
        try:
            output = json.loads(process.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Validator did not return JSON: " + process.stderr) from exc
        return process.returncode, output

    code, baseline = run(args.tables_dir, args.empirical_table)
    cases = [{"case": "unchanged_control", "expected": "MATCH with exit0",
              "exit_code": code, "reviewer_requested_h2_agreement": baseline.get("reviewer_requested_h2_agreement"),
              "test_passed": code == 0 and baseline.get("reviewer_requested_h2_agreement") == "MATCH"}]
    temp_parent = Path(__file__).parent / "temporary_negative_tests"
    temp_parent.mkdir(exist_ok=True)
    try:
        for name, expected_failure in (
                ("changed_beta", "H2.all.coefficient"),
                ("changed_floor", "scenario.all.neutral.step.floor_vs_curves"),
                ("missing_file", "required_file.EMPIRICAL_RESPONSE_SPECIFICATIONS.csv")):
            with tempfile.TemporaryDirectory(prefix=name + "_", dir=temp_parent) as temporary:
                tables = Path(temporary)
                for filename in FILES:
                    source = args.empirical_table if filename == FILES[2] and args.empirical_table else args.tables_dir / filename
                    shutil.copy2(source, tables / filename)
                if name == "changed_beta":
                    change_row(tables / FILES[0],
                               lambda r: r["cohort"] == "full" and r["group"] == "all" and r["model"] == "TWFE",
                               "coefficient", lambda value: str(float(value) + 0.01))
                elif name == "changed_floor":
                    change_row(tables / FILES[1],
                               lambda r: r["candidate_group"] == "all" and r["background"] == "neutral" and r["scenario"] == "step",
                               "first_success_fraction", lambda value: "0.4")
                else:
                    (tables / FILES[2]).unlink()
                code, result = run(tables)
                observed = [f["check"] for f in result.get("failures", [])]
                passed = (code == 1 and result.get("reviewer_requested_h2_agreement") == "FAIL"
                          and expected_failure in observed
                          and result.get("full_manuscript_reproduction") == "NOT_ESTABLISHED")
                cases.append({"case": name, "expected_failure": expected_failure,
                              "exit_code": code, "observed_failure_codes": observed,
                              "reviewer_requested_h2_agreement": result.get("reviewer_requested_h2_agreement"),
                              "test_passed": passed})
    finally:
        temp_parent.rmdir()
    result = {"test_scope": "Validator control and rejection behaviour on copies; no scientific analysis rerun",
              "all_required_tests_passed": all(case["test_passed"] for case in cases),
              "full_manuscript_reproduction": "NOT_ESTABLISHED", "cases": cases}
    encoded = json.dumps(result, indent=2) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0 if result["all_required_tests_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
