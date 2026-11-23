#!/usr/bin/env python3
"""Strict, independent comparison of the ten required reviewer output tables.

Compares saved-evidence replay outputs with archived results. A pass does not
establish that the external raw archive or the original simulation was rerun.
The producer's scientific code is neither imported nor modified.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np
import pandas as pd

RTOL = ATOL = 1e-10
TABLE_KEYS = {
    "FINAL_RESULTS.csv": ["result_id"],
    "RECOVERY_CURVES.csv": ["result_id", "dose_fraction"],
    "RESULT_TO_SOURCE_LEDGER.csv": ["result_id"],
    "CALIBRATION_TARGETS.csv": ["cohort", "group", "model", "scale"],
    "PRIMARY_SCENARIO_RESULTS.csv": ["result_id"],
    "FIGURE4_DATA.csv": ["result_id"],
    "GRAPHICAL_ABSTRACT_DATA.csv": ["result_id"],
    "MATCHED_COMPARISONS.csv": ["result_id"],
    "BASELINES_AND_DENOMINATORS.csv": ["cohort", "group", "model"],
    "WEIGHT_FUNCTION_CHECKS.csv": ["cohort", "group", "model"],
}
PATH_COLUMNS = ("coefficient_evidence", "coefficient_array", "calibration_evidence")


def read_table(path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    # Preserve literal text independently of pandas' numeric/NA inference.
    with path.open(newline="", encoding="utf-8-sig") as stream:
        header = next(csv.reader(stream), [])
    if not header or len(header) != len(set(header)):
        raise ValueError("Missing or duplicate CSV column names")
    numeric = pd.read_csv(path)
    literal = pd.read_csv(path, dtype=str, keep_default_na=False)
    return numeric, literal


def compare_table(name: str, keys: list[str], generated: Path, reference: Path) -> dict:
    rec = {
        "file": name, "status": "FAIL", "passed": False,
        "generated_rows": None, "reference_rows": None,
        "generated_columns": None, "reference_columns": None,
        "generated_cells": 0, "reference_cells": 0, "compared_cells": 0,
        "aligned_by": keys, "same_shape": False, "same_columns": False,
        "same_keys": False, "os_path_separators_normalized_in": [],
        "numeric_columns_compared": 0, "text_columns_compared": 0,
        "numeric_difference_count": 0, "text_difference_count": 0,
        "numeric_differences": [], "text_differences": [],
        "max_abs_numeric_difference": None, "errors": [],
    }
    tables = {}
    for label, folder in (("generated", generated), ("reference", reference)):
        path = folder / name
        if not path.is_file():
            rec["errors"].append(f"Missing {label} table: {name}")
            continue
        try:
            tables[label] = read_table(path)
            frame = tables[label][0]
            rec[f"{label}_rows"] = len(frame)
            rec[f"{label}_columns"] = len(frame.columns)
            rec[f"{label}_cells"] = int(frame.size)
            if frame.empty:
                rec["errors"].append(f"{label} table has no data rows")
        except (OSError, ValueError, pd.errors.ParserError) as exc:
            rec["errors"].append(f"Cannot read {label} table: {type(exc).__name__}: {exc}")
    if len(tables) != 2:
        return rec
    x, x_text = tables["generated"]
    y, y_text = tables["reference"]
    rec["same_shape"] = x.shape == y.shape
    rec["same_columns"] = list(x.columns) == list(y.columns)
    if not rec["same_shape"]:
        rec["errors"].append(f"Shape differs: generated {x.shape}, reference {y.shape}")
    if not rec["same_columns"]:
        rec["missing_columns"] = [c for c in y.columns if c not in x.columns]
        rec["extra_columns"] = [c for c in x.columns if c not in y.columns]
        rec["errors"].append("CSV columns or their order differ")
    for label, frame in (("generated", x), ("reference", y)):
        missing = [key for key in keys if key not in frame.columns]
        if missing:
            rec["errors"].append(f"Missing {label} matching keys: {missing}")
        elif frame[keys].isna().any().any():
            rec["errors"].append(f"Missing values in {label} matching keys")
        elif frame.duplicated(keys).any():
            rec["errors"].append(f"Duplicate {label} matching keys")
    if rec["errors"]:
        return rec

    # Same alignment hierarchy as compare_replay.py, now fixed per required table.
    x_order = x.sort_values(keys, kind="mergesort").index
    y_order = y.sort_values(keys, kind="mergesort").index
    x, x_text = (frame.loc[x_order].reset_index(drop=True) for frame in (x, x_text))
    y, y_text = (frame.loc[y_order].reset_index(drop=True) for frame in (y, y_text))
    x_keys = pd.MultiIndex.from_frame(x[keys])
    y_keys = pd.MultiIndex.from_frame(y[keys])
    rec["same_keys"] = x_keys.equals(y_keys)
    if not rec["same_keys"]:
        rec["errors"].append("Matching key values differ")
        rec["generated_only_key_count"] = len(x_keys.difference(y_keys, sort=False))
        rec["reference_only_key_count"] = len(y_keys.difference(x_keys, sort=False))
        return rec

    for column in PATH_COLUMNS:
        if column in x.columns:
            x_text[column] = x_text[column].str.replace("\\", "/", regex=False)
            y_text[column] = y_text[column].str.replace("\\", "/", regex=False)
            rec["os_path_separators_normalized_in"].append(column)

    maximum = 0.0
    infinite_difference = False
    for column in x.columns:
        numeric = (
            pd.api.types.is_numeric_dtype(x[column])
            and pd.api.types.is_numeric_dtype(y[column])
            and not pd.api.types.is_bool_dtype(x[column])
            and not pd.api.types.is_bool_dtype(y[column])
        )
        if numeric:
            rec["numeric_columns_compared"] += 1
            left, right = x[column].to_numpy(), y[column].to_numpy()
            close = np.isclose(left, right, rtol=RTOL, atol=ATOL, equal_nan=True)
            difference_count = int(np.count_nonzero(~close))
            with np.errstate(invalid="ignore", over="ignore"):
                absolute = np.abs(left.astype(float) - right.astype(float))
            finite = absolute[np.isfinite(absolute)]
            if finite.size:
                maximum = max(maximum, float(finite.max()))
            infinite_difference = infinite_difference or bool(np.isinf(absolute).any())
            if difference_count:
                rec["numeric_differences"].append({"column": column, "cells": difference_count})
                rec["numeric_difference_count"] += difference_count
        else:
            rec["text_columns_compared"] += 1
            difference_count = int((x_text[column] != y_text[column]).sum())
            if difference_count:
                rec["text_differences"].append({"column": column, "cells": difference_count})
                rec["text_difference_count"] += difference_count
    rec["compared_cells"] = int(x.size)
    # JSON has no Infinity literal; retain an explicit string if it occurs.
    rec["max_abs_numeric_difference"] = "Infinity" if infinite_difference else maximum
    rec["passed"] = not (rec["numeric_difference_count"] or rec["text_difference_count"])
    rec["status"] = "PASS" if rec["passed"] else "FAIL"
    return rec


def compare(generated: Path, reference: Path) -> dict:
    tables = []
    for name, keys in TABLE_KEYS.items():
        try:
            tables.append(compare_table(name, keys, generated, reference))
        except Exception as exc:
            # A malformed table must fail while the other nine are still reported.
            tables.append({
                "file": name, "status": "FAIL", "passed": False,
                "generated_cells": 0, "reference_cells": 0, "compared_cells": 0,
                "max_abs_numeric_difference": None,
                "errors": [f"Comparison error: {type(exc).__name__}: {exc}"],
            })
    return {
        "status": "PASS" if all(table["passed"] for table in tables) else "FAIL",
        "scope": "Saved-evidence replay against archived tables; not a raw reconstruction",
        "relative_tolerance": RTOL, "absolute_tolerance": ATOL, "equal_nan": True,
        "required_table_count": len(TABLE_KEYS),
        "passed_table_count": sum(table["passed"] for table in tables),
        "failed_table_count": sum(not table["passed"] for table in tables),
        "total_cells": sum(table["compared_cells"] for table in tables),
        "total_generated_cells": sum(table["generated_cells"] for table in tables),
        "total_reference_cells": sum(table["reference_cells"] for table in tables),
        "tables": tables,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generated", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    report = compare(args.generated, args.reference)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"{report['status']}: {report['passed_table_count']}/{report['required_table_count']} "
          f"required tables; {report['total_cells']} compared cells")
    for table in report["tables"]:
        if not table["passed"]:
            print(f"  FAIL {table['file']}: " + "; ".join(table.get("errors", []))
                  + f"; numeric differences={table.get('numeric_difference_count', 0)}"
                  + f"; text differences={table.get('text_difference_count', 0)}")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
