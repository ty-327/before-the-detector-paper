#!/usr/bin/env python3
"""Check retained H2 tables against the current Revision 1 claims, using stdlib only.

This is an arithmetic/claim validator, not a model refit or raw-data reproduction.
Input files are read only. Exit 0 means the stated, limited checks agree; exit 1
means an input or numerical check failed. Full-manuscript reproduction is never
reported as established by this program.
"""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import re
from statistics import NormalDist
import xml.etree.ElementTree as ET
import zipfile

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
RAW_ABS_TOL = 1e-10
RAW_REL_TOL = 1e-9
DISPLAY_COEFFICIENT_TOL = 0.000050001
DISPLAY_PERCENT_TOL = 0.005000001
TABLE_FILES = (
    "BASELINES_AND_DENOMINATORS.csv", "PRIMARY_SCENARIO_RESULTS.csv",
    "EMPIRICAL_RESPONSE_SPECIFICATIONS.csv", "RECOVERY_CURVES.csv",
)


class InputFailure(Exception):
    def __init__(self, check, detail):
        self.check, self.detail = check, detail


class Checks:
    def __init__(self):
        self.failures = []
        self.count = 0

    def require(self, condition, code, actual=None, expected=None):
        self.count += 1
        if not condition:
            self.failures.append({"check": code, "actual": actual, "expected": expected})

    def near(self, actual, expected, code, atol=RAW_ABS_TOL, rtol=RAW_REL_TOL):
        try:
            a, b = float(actual), float(expected)
            okay = math.isfinite(a) and math.isfinite(b) and math.isclose(a, b, abs_tol=atol, rel_tol=rtol)
        except (TypeError, ValueError):
            okay = False
        self.require(okay, code, actual, expected)


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_file(path):
    if not path.is_file():
        raise InputFailure("required_file." + path.name, "Missing input file: " + str(path))
    return path.read_bytes()


def read_csv(path):
    read_file(path)
    with path.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise InputFailure("nonempty_table." + path.name, "Table has no data rows")
    return rows


def one(rows, criteria, code):
    found = [r for r in rows if all(r.get(k) == v for k, v in criteria.items())]
    if len(found) != 1:
        raise InputFailure(code, "Expected exactly one row; found " + str(len(found)))
    return found[0]


def number(value):
    n = float(value)
    if not math.isfinite(n):
        raise ValueError("Non-finite numerical input")
    return n


def normalized(text):
    return " ".join(text.replace("−", "-").split())


def element_text(element):
    return normalized("".join(n.text or "" for n in element.iter(W + "t")))


def read_manuscript(path):
    read_file(path)
    with zipfile.ZipFile(path) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    body = root.find(W + "body")
    tables, caption = {}, None
    for element in body:
        if element.tag == W + "p":
            text = element_text(element)
            for name in ("A2", "A3"):
                if text.startswith(("Appendix Table " + name + ".", "Appendix Table A." + name[1:] + ".")):
                    caption = name
        elif element.tag == W + "tbl" and caption:
            if caption in tables:
                raise InputFailure("manuscript_table." + caption, "Duplicate appendix table")
            tables[caption] = [[element_text(cell) for cell in row.findall(W + "tc")]
                               for row in element.findall(W + "tr")]
            caption = None
    for name in ("A2", "A3"):
        if name not in tables:
            raise InputFailure("manuscript_table." + name, "Required appendix table missing")
    return "\n".join(element_text(p) for p in root.iter(W + "p")), tables


def numeric_cells(cell, signed=False):
    pattern = r"[-+]?\d+(?:\.\d+)?" if signed else r"\d+(?:\.\d+)?"
    return [float(n) for n in re.findall(pattern, normalized(cell))]


def compare_vector(checks, actual, expected, code, tol):
    checks.require(len(actual) == len(expected), code + ".length", len(actual), len(expected))
    for i, (a, b) in enumerate(zip(actual, expected)):
        checks.near(a, b, code + "." + str(i), atol=tol, rtol=0)


def wilson(k, n):
    p, z = k / n, NormalDist().inv_cdf(0.975)
    denominator = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denominator
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
    return centre - half, centre + half


def check_curve_row(checks, row, repetitions, code):
    k, n = number(row["recovered"]), number(row["repetitions"])
    if n <= 0 or not 0 <= k <= n or not k.is_integer() or not n.is_integer():
        raise InputFailure(code + ".counts", "Counts must be integers with 0 <= recovered <= repetitions")
    checks.near(n, repetitions, code + ".repetitions", rtol=0)
    p = k / n
    lo, hi = wilson(k, n)
    checks.near(row["probability"], p, code + ".probability")
    checks.near(row["wilson_low"], lo, code + ".wilson_low")
    checks.near(row["wilson_high"], hi, code + ".wilson_high")
    checks.near(row["mcse"], math.sqrt(p * (1 - p) / n), code + ".mcse")
    return {"dose": number(row["dose_fraction"]), "recovered": int(k),
            "repetitions": int(n), "probability": p, "wilson_low": lo, "wilson_high": hi}


def validate(args, report, checks):
    spec = json.loads(read_file(args.targets))
    if spec.get("schema_version") != 1:
        raise InputFailure("target_schema", "Expected schema_version 1")
    report["target_specification_sha256"] = sha256(args.targets)
    report["limitations"] = spec["limits"]
    report["source_identities"] = {}
    for key, path in (("manuscript", args.manuscript), ("reviewer_xlsx", args.reviewer_xlsx)):
        read_file(path)
        actual = sha256(path)
        expected = spec["source_documents"][key]["sha256"]
        checks.require(actual == expected, "source_identity." + key, actual, expected)
        report["source_identities"][key] = {"sha256": actual, "matches_target": actual == expected}
    manuscript_text, manuscript_tables = read_manuscript(args.manuscript)
    table_paths = {name: args.tables_dir / name for name in TABLE_FILES}
    if args.empirical_table:
        table_paths[TABLE_FILES[2]] = args.empirical_table
    tables = {name: read_csv(path) for name, path in table_paths.items()}
    key_turnover = json.loads(read_file(args.key_turnover))
    report["input_sha256"] = {name: sha256(path) for name, path in table_paths.items()}
    report["input_sha256"]["KEY_TURNOVER.json"] = sha256(args.key_turnover)
    report["numerical_input_sources"] = {
        "summary_tables": {"origin_declared": args.tables_origin, "directory": str(args.tables_dir),
                           "activity": "Summary arithmetic and claims checked; no model refit by this validator"},
        "empirical_profile_fits": {"origin": "retained_empirical_fits", "path": str(table_paths[TABLE_FILES[2]]),
                                   "sha256": report["input_sha256"][TABLE_FILES[2]],
                                   "activity": "Retained coefficients, SEs and intervals compared; not refitted or recomputed during summary replay"}}

    baselines, empirical = {}, {}
    for group, target in spec["baseline"].items():
        row = one(tables[TABLE_FILES[0]], {"cohort": "full", "group": group, "model": "TWFE"},
                  "H2." + group + ".row")
        baselines[group] = row
        for field, expected in target.items():
            if field in ("pre_units", "candidate_items", "control_items", "n", "items", "dates", "rank"):
                checks.near(row[field], expected, "H2." + group + "." + field, atol=0, rtol=0)
            else:
                checks.near(row[field], expected, "H2." + group + "." + field)
        checks.near(row["percent_log_transform"], 100 * math.expm1(number(row["coefficient"])),
                    "H2." + group + ".derived_percent")
    h2 = baselines["all"]
    match = re.search(r"requested item and calendar-date model gives a coefficient of ([-\d.]+) "
                      r"\(item/date-clustered SE ([\d.]+); 95% interval ([-\d.]+) to ([-\d.]+)\), "
                      r"equivalent to ([-\d.]+)%", manuscript_text)
    if not match:
        raise InputFailure("manuscript.H2.statement", "Current requested-model result statement not found")
    for i, field in enumerate(("coefficient", "se_two_way", "ci_low_two_way", "ci_high_two_way", "percent_log_transform")):
        checks.near(match.group(i + 1), h2[field], "manuscript.H2." + field,
                    atol=DISPLAY_PERCENT_TOL if i == 4 else DISPLAY_COEFFICIENT_TOL, rtol=0)

    for profile in spec["profiles"]:
        scenario = profile["scenario"]
        for group in spec["baseline"]:
            target = profile["empirical"][group]
            code = "empirical." + group + "." + scenario
            if target["coefficient"] is None:
                checks.require(not any(r["candidate_group"] == group and r["shape"] == "delay28"
                                       for r in tables[TABLE_FILES[2]]), code + ".not_estimable")
                continue
            row = one(tables[TABLE_FILES[2]], {"candidate_group": group, "shape": target["shape"]}, code + ".row")
            empirical[(group, scenario)] = row
            for field in ("coefficient", "se_two_way", "ci_low_two_way", "ci_high_two_way"):
                checks.near(row[field], target[field], code + "." + field)
            checks.near(row["dates"], 42, code + ".dates", rtol=0)
            checks.near(row["percent_log_transform"], 100 * math.expm1(number(row["coefficient"])), code + ".derived_percent")

    selection = spec["selection"]
    fixed = {k: selection[k] for k in ("cohort", "model", "scale", "implementation", "calibration")}
    profiles = {p["scenario"]: p for p in spec["profiles"]}
    groups = tuple(spec["baseline"])
    summary_rows = [r for r in tables[TABLE_FILES[1]] if all(r.get(k) == v for k, v in fixed.items())
                    and r["candidate_group"] in groups and r["scenario"] in profiles]
    curve_rows = [r for r in tables[TABLE_FILES[3]] if all(r.get(k) == v for k, v in fixed.items())
                  and r["candidate_group"] in groups and r["scenario"] in profiles]
    results = {}
    for group in groups:
        for background in ("neutral", "observed"):
            for scenario, profile in profiles.items():
                code = "scenario." + ".".join((group, background, scenario))
                criteria = {"candidate_group": group, "background": background, "scenario": scenario}
                summary = one(summary_rows, criteria, code + ".row")
                rows = [r for r in curve_rows if all(r[k] == v for k, v in criteria.items())]
                rows.sort(key=lambda r: number(r["dose_fraction"]))
                doses = [number(r["dose_fraction"]) for r in rows]
                if len(doses) != len(set(doses)):
                    raise InputFailure(code + ".doses", "Duplicate dose row")
                compare_vector(checks, doses, spec["grid_fractions"], code + ".grid", 1e-12)
                for field in ("window_start", "window_end", "post_start"):
                    checks.require(summary[field] == selection[field], code + "." + field, summary[field], selection[field])
                checks.near(summary["selected_candidate_items"], selection["selected_candidate_items"][group], code + ".selected_candidates", atol=0, rtol=0)
                checks.near(summary["selected_control_items"], selection["selected_control_items"], code + ".selected_controls", atol=0, rtol=0)
                for field, base_field in (("candidate_items", "candidate_items"), ("control_items", "control_items"),
                                         ("pre_volume_denominator", "pre_units"), ("baseline_coefficient", "coefficient")):
                    checks.near(summary[field], baselines[group][base_field], code + "." + field,
                                atol=RAW_ABS_TOL if field == "baseline_coefficient" else 0,
                                rtol=RAW_REL_TOL if field == "baseline_coefficient" else 0)
                curves = [check_curve_row(checks, row, spec["repetitions"], code + ".dose" + str(i)) for i, row in enumerate(rows)]
                qualifying = [r for r in curves if r["probability"] >= spec["recovery_target"]]
                floor = qualifying[0]["dose"] if qualifying else None
                expected = profile["floors"][group + "_" + background]
                checks.require(summary["status"] == expected["status"], code + ".status", summary["status"], expected["status"])
                if expected["floor_fraction"] is None:
                    checks.require(floor is None and summary["first_success_fraction"] == "", code + ".no_floor", floor, None)
                    for row in rows:
                        checks.near(row["mean_added_units"], 0, code + ".zero_exposure", rtol=0)
                    results[(group, background, scenario)] = {"floor": None, "summary": summary}
                    continue
                if floor is None:
                    raise InputFailure(code + ".floor", "No tested dose reaches the recovery target")
                checks.near(floor, expected["floor_fraction"], code + ".floor_target", rtol=0)
                checks.near(summary["first_success_fraction"], floor, code + ".floor_vs_curves", rtol=0)
                upper = qualifying[0]
                position = curves.index(upper)
                if position == 0:
                    raise InputFailure(code + ".lower_dose", "Current target requires a preceding tested dose")
                lower = curves[position - 1]
                checks.near(summary["lower_dose_fraction"], lower["dose"], code + ".lower_dose", rtol=0)
                for prefix, curve in (("zero", curves[0]), ("lower", lower), ("upper", upper)):
                    for field in ("recovered", "repetitions", "probability", "wilson_low", "wilson_high"):
                        checks.near(summary[prefix + "_" + field], curve[field], code + "." + prefix + "_" + field)
                results[(group, background, scenario)] = {"floor": floor, "lower_dose": lower["dose"],
                                                          "crossing": upper, "summary": summary}

    a2 = manuscript_tables["A2"]
    if len(a2) != 5 or any(len(row) != 6 for row in a2):
        raise InputFailure("manuscript.A2.shape", "Expected header plus four rows and six columns")
    derived_a2 = []
    labels = ("All candidates; neutral", "All candidates; observed", "Exclude 29 containers; neutral", "Exclude 29 containers; observed")
    for i, target in enumerate(spec["abrupt_targets"]):
        group, background = target["candidate_group"], target["background"]
        result = results[(group, background, "step")]
        summary, crossing = result["summary"], result["crossing"]
        for field in ("upper_probability", "upper_wilson_low", "upper_wilson_high", "conditional_mc_p025", "conditional_mc_p975", "threshold"):
            checks.near(summary[field], target[field], "A2." + group + "." + background + "." + field)
        values = [[100 * result["floor"]], [100 * crossing["probability"]],
                  [100 * crossing["wilson_low"], 100 * crossing["wilson_high"]],
                  [100 * result["lower_dose"], 100 * result["floor"]],
                  [100 * number(summary["conditional_mc_p025"]), 100 * number(summary["conditional_mc_p975"])]]
        checks.require(a2[i + 1][0] == labels[i], "manuscript.A2.label." + str(i), a2[i + 1][0], labels[i])
        for column, expected in enumerate(values, 1):
            compare_vector(checks, numeric_cells(a2[i + 1][column]), expected, "manuscript.A2." + str(i) + "." + str(column),
                           DISPLAY_PERCENT_TOL if column in (2, 3) else 1e-9)
        derived_a2.append({"group": group, "background": background, "floor_percent": values[0][0],
                           "recovery_percent": values[1][0], "wilson_percent": values[2],
                           "adjacent_doses_percent": values[3], "retained_conditional_range_percent": values[4]})

    a3 = manuscript_tables["A3"]
    if len(a3) != 9 or any(len(row) != 5 for row in a3):
        raise InputFailure("manuscript.A3.shape", "Expected header plus eight rows and five columns")
    derived_a3 = []
    for i, profile in enumerate(spec["profiles"]):
        scenario, actual = profile["scenario"], a3[i + 1]
        checks.require(actual[0] == profile["label"], "manuscript.A3.label." + str(i), actual[0], profile["label"])
        display = {"profile": scenario}
        for j, group in enumerate(groups):
            floor_values = [results[(group, b, scenario)]["floor"] for b in ("neutral", "observed")]
            if floor_values[0] is None:
                checks.require(actual[j + 1] == "No in-window exposure", "manuscript.A3." + group + ".delay28.floor")
                checks.require(actual[j + 3] == "Not estimable", "manuscript.A3." + group + ".delay28.coefficient")
                display[group] = {"floors_percent": None, "coefficient": None, "se_two_way": None}
                continue
            compare_vector(checks, numeric_cells(actual[j + 1]), [100 * x for x in floor_values], "manuscript.A3." + group + "." + scenario + ".floors", 1e-9)
            row = empirical[(group, scenario)]
            values = [number(row["coefficient"]), number(row["se_two_way"])]
            compare_vector(checks, numeric_cells(actual[j + 3], signed=True), values, "manuscript.A3." + group + "." + scenario + ".empirical", DISPLAY_COEFFICIENT_TOL)
            display[group] = {"floors_percent": [100 * x for x in floor_values], "coefficient": values[0], "se_two_way": values[1]}
        derived_a3.append(display)

    key_units = number(key_turnover["pre21_whole_word_key_units"])
    checks.near(key_units, spec["key_pre_units"], "benchmark.key_units", rtol=0)
    full_units, excluded_units = number(baselines["all"]["pre_units"]), number(baselines["exclude_cases"]["pre_units"])
    benchmarks = [key_units, full_units, 100 * key_units / full_units, excluded_units, 100 * key_units / excluded_units]
    match = re.search(r"Recorded key turnover is ([\d,]+) units against ([\d,]+) candidate units before the event, or ([\d.]+)%\. "
                      r"Excluding the containers reduces the candidate denominator to ([\d,]+) units and raises that benchmark to ([\d.]+)%", manuscript_text)
    if not match:
        raise InputFailure("manuscript.benchmark.statement", "Current key/candidate benchmark statement not found")
    for i, expected in enumerate(benchmarks):
        checks.near(match.group(i + 1).replace(",", ""), expected, "manuscript.benchmark." + str(i),
                    atol=DISPLAY_PERCENT_TOL if i in (2, 4) else 1e-9, rtol=0)
    report["checked_rows"] = {"baseline_groups": 2, "empirical_profiles": len(empirical),
                              "requested_scenarios": len(results), "recovery_curve_rows": len(curve_rows),
                              "manuscript_A2_rows": 4, "manuscript_A3_rows": 8}
    report["derived"] = {"H2": {field: number(h2[field]) for field in ("coefficient", "se_two_way", "ci_low_two_way", "ci_high_two_way", "percent_log_transform")},
                         "benchmarks_percent": {"all": benchmarks[2], "exclude_containers": benchmarks[4]},
                         "A2": derived_a2, "A3": derived_a3}
    empirical_failures = [f for f in checks.failures if f["check"].startswith("empirical.")
                          or (f["check"].startswith("manuscript.A3.") and ".empirical." in f["check"])]
    source_mismatch = any(f["check"].startswith("source_identity.") for f in checks.failures)
    report["agreement_components"] = {
        "summary_table_claims": {"status": "FAIL" if source_mismatch or len(checks.failures) > len(empirical_failures) else "MATCH",
                                 "origin_declared": args.tables_origin,
                                 "scope": "H2 baseline, A2/A3 floors, recovery arithmetic and turnover ratios; no refit"},
        "retained_empirical_fit_claims": {"status": "FAIL" if source_mismatch or empirical_failures else "MATCH",
                                          "origin": "retained_empirical_fits",
                                          "scope": "A3 retained coefficient/SE/interval comparison; no fresh empirical refit"}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manuscript", type=Path, required=True)
    parser.add_argument("--reviewer-xlsx", type=Path, required=True)
    parser.add_argument("--tables-dir", type=Path, required=True)
    parser.add_argument("--empirical-table", type=Path,
                        help="Explicit retained empirical-fit CSV; defaults to the file in --tables-dir")
    parser.add_argument("--tables-origin", choices=("retained", "saved-evidence-replay"), default="retained",
                        help="Provenance label for the supplied summary tables; does not assert a raw-data refit")
    parser.add_argument("--key-turnover", type=Path, required=True)
    parser.add_argument("--targets", type=Path, default=Path(__file__).with_name("revision1_targets.json"))
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = {"validation_scope": "Retained-table arithmetic and current Revision1 H2 claim agreement; no model refit or raw-data rerun",
              "full_manuscript_reproduction": "NOT_ESTABLISHED"}
    checks = Checks()
    try:
        validate(args, report, checks)
    except InputFailure as exc:
        checks.failures.append({"check": exc.check, "detail": exc.detail})
    except (OSError, ValueError, TypeError, KeyError, IndexError, OverflowError,
            csv.Error, zipfile.BadZipFile, ET.ParseError) as exc:
        checks.failures.append({"check": "input_format", "detail": str(exc)})
    report.update({"reviewer_requested_h2_agreement": "FAIL" if checks.failures else "MATCH",
                   "failure_count": len(checks.failures), "failures": checks.failures})
    encoded = json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 1 if checks.failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
