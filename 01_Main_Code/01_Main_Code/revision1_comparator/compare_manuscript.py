#!/usr/bin/env python3
"""Compare defined Revision 1 historical claims; never fit or alter analyses.

This replaces the invalid corpus-count/S1b-arm comparison. A missing result is
NOT_VERIFIED, not agreement. --run preserves the existing full-run CLI.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import statistics
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RAW_SHA256 = "e00557bd8dc6d5e1a09f8da36213039ac23950f9613e245db49c6ef564ce6df7"
CORPUS_SOURCE_SHA256 = "1d5ceb2fb584dcbadce3e218a37c9cd3c6218bd102c77101a0d7dd6bf0587cd9"
TY_DATA_PATHS = {
    "evidence/h3_index_construction.csv": "provenance/H3_INDEX_CONSTRUCTION_source.csv",
    "evidence/historical_s1b_results.txt": "provenance/historical_S1b_results.txt",
    "evidence/historical_s1b_spikes.csv": "data/S1b/historical_spikes.csv",
    "evidence/historical_raw_filenames.json": "data/S1b/historical_raw_filenames.json",
}
H3_SELECTOR = {
    "scope": "full_zip", "keys": "whole_word_27keys",
    "recipe": "equal_item_daily_mean_then_equal_days",
}
H3_TARGETS = {
    "price_2017_2018_min": 2.03, "price_2017_2018_max": 2.10,
    "price_2020": 4.82, "price_2023": 10.57, "price_2024": 9.36,
    "ratio_2017_2018_min": 5.4, "ratio_2017_2018_max": 5.6,
    "ratio_2020_2024_min": 4.8, "ratio_2020_2024_max": 6.7,
}
CORPUS_DEFINITION = {
    "population": "all_item_histories",
    "price_filter": "full_sample_mean_raw_price_gt_10",
    "minimum_valid_raw_rows": 1,
    "minimum_observed_daily_prices": 2,
    "day_definition": "unix_timestamp_utc_day",
    "daily_price": "quantity_weighted_mean_of_raw_price_summaries",
    "return_rule": "absolute_pct_change_between_observed_days_gt_1",
    "s1b_category_filter": False,
}


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def decode_text(path: Path) -> str:
    data = path.read_bytes()
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252")


def claim(name, status, expected=None, actual=None, scope="", note=""):
    return dict(claim=name, status=status, expected=expected, actual=actual,
                scope=scope, note=note)


def rounded_claim(name, expected, actual, places, scope):
    value = Decimal(str(actual))
    if not value.is_finite():
        return claim(name, "NOT_VERIFIED", expected, None, scope, "Nonfinite value")
    shown = value.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)
    return claim(name, "PASS" if shown == Decimal(str(expected)) else "MISMATCH",
                 expected, float(value), scope,
                 f"Ordinary {places}-decimal display: {shown}; no enlarged tolerance")


def evidence_path(root: Path, relative: str, data_dir: Path | None = None):
    if data_dir is not None and relative in TY_DATA_PATHS:
        return data_dir / TY_DATA_PATHS[relative]
    return root / relative


def check_provenance(root: Path, data_dir: Path | None = None, run: Path | None = None):
    provenance = json.loads((root / "SOURCE_PROVENANCE.json").read_text())
    missing, changed, checked = [], [], []
    for record in provenance["files"]:
        # Fresh-run outputs are compared numerically below. They must not be
        # required to have the byte serialization of retained output copies.
        if run is not None and record["path"].startswith("evidence/"):
            continue
        path = evidence_path(root, record["path"], data_dir)
        checked.append(record["path"])
        if not path.is_file():
            missing.append(record["path"])
        elif path.stat().st_size != record["bytes"] or digest(path) != record["sha256"]:
            changed.append(record["path"])
    status = "MISMATCH" if changed else ("NOT_VERIFIED" if missing else "PASS")
    return provenance, claim("Retained-source integrity", status,
        "Every required retained source matches its archived bytes",
        {"missing": missing, "changed": changed, "checked_files": checked},
        "Integrity of retained evidence; not independent authentication of its scientific truth")


def check_s1b(summary_path: Path, spikes_path: Path, names_path: Path):
    scope = "Historical 22,420-file inventory; original S1b arms and >=30-row/day eligibility"
    try:
        names = json.loads(names_path.read_text())
        if not isinstance(names, list) or len(names) != 22420 or len(set(names)) != len(names):
            raise ValueError("Historical filename inventory is missing, duplicated or has the wrong size")
        text = decode_text(summary_path)
        primary = text.split("PRIMARY", 1)[1].split("SECONDARY", 1)[0]
        matches = re.findall(
            r"^\s+(FUNGIBLE|NON-FUNGIBLE)[^\n]*\n\s+spikes:\s*([\d,]+)\s+"
            r"item-days:\s*([\d,]+)\s+rate:\s*([\d.]+)", primary, re.M)
        if len(matches) != 2 or {m[0] for m in matches} != {"FUNGIBLE", "NON-FUNGIBLE"}:
            raise ValueError("Exactly two historical primary-arm result blocks are required")
        blocks = {("fungible" if m[0] == "FUNGIBLE" else "nonfungible"):
                  (int(m[1].replace(",", "")), int(m[2].replace(",", "")), m[3]) for m in matches}
        counts = Counter()
        fungible_units, fungible_reverted = [], 0
        with spikes_path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            required = {"arm", "mean_price_gt10", "reverted_3d", "units_at_spike"}
            if not required.issubset(reader.fieldnames or []):
                raise ValueError("Required historical spike columns are absent")
            for row in reader:
                if row["mean_price_gt10"] not in {"True", "False"}:
                    raise ValueError("Invalid price-eligibility flag")
                if row["mean_price_gt10"] == "False":
                    continue
                arm = row["arm"]
                if arm not in blocks or row["reverted_3d"] not in {"True", "False"}:
                    raise ValueError("Invalid historical arm or reversion flag")
                counts[arm] += 1
                if arm == "fungible":
                    fungible_units.append(float(row["units_at_spike"]))
                    fungible_reverted += row["reverted_3d"] == "True"
        if any(blocks[a][1] <= 0 or counts[a] == 0 for a in blocks):
            raise ValueError("Positive arm counts and denominators are required")
        count_match = all(blocks[a][0] == counts[a] for a in blocks)
        results = [claim("Historical S1b row-count reconciliation", "PASS" if count_match else "MISMATCH",
            {a: blocks[a][0] for a in blocks}, dict(counts), scope,
            "The restricted-arm total is descriptive only; it is not compared with the corpus-wide 25,432 claim")]
        for arm, target in [("fungible", 2.21), ("nonfungible", 2.75)]:
            rate = 1000 * counts[arm] / blocks[arm][1]
            results.append(rounded_claim(f"Historical S1b {arm} rate per 1,000", target, rate, 2, scope))
        results.append(rounded_claim("Historical S1b fungible reversion percent", 8.0,
            100 * fungible_reverted / counts["fungible"], 1, scope))
        median = statistics.median(fungible_units)
        results.append(claim("Historical S1b median fungible spike units",
            "PASS" if median == 1 else "MISMATCH", 1, median, scope))
        return results
    except (OSError, ValueError, KeyError, IndexError, TypeError) as exc:
        return [claim("Historical S1b evidence", "NOT_VERIFIED", scope=scope, note=str(exc))]


def read_manuscript_h3_targets(path: Path):
    """Read the existing H3 results paragraph from the delivered clean DOCX."""
    with zipfile.ZipFile(path) as archive:
        document = ET.fromstring(archive.read("word/document.xml"))
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    paragraphs = ["".join(node.itertext()) for node in document.findall(".//w:p", ns)]
    selected = [text for text in paragraphs if text.startswith("Legacy keys appreciated sharply,")]
    if len(selected) != 1:
        raise ValueError("Require exactly one H3 results paragraph in the clean manuscript")
    text = selected[0]
    prices = re.search(
        r"Average key prices were between USD ([\d.]+) and USD ([\d.]+) in 2017 and 2018, "
        r"then rose to USD ([\d.]+) in 2020 and USD ([\d.]+) in 2023 \(USD ([\d.]+) in 2024\)", text)
    ratios = re.search(
        r"ratio of key prices to the index stayed within overlapping ranges: ([\d.]+) to ([\d.]+) "
        r"in the two years before the intervention and ([\d.]+) to ([\d.]+) afterward", text)
    if prices is None or ratios is None:
        raise ValueError("The H3 price and ratio statements could not be read from the clean manuscript")
    return dict(zip(H3_TARGETS, map(float, (*prices.groups(), *ratios.groups()))))


def check_h3(path: Path, targets=None):
    scope = "full_zip; whole_word_27keys; equal_item_daily_mean_then_equal_days"
    targets = H3_TARGETS if targets is None else targets
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        selected = [r for r in rows if all(r.get(k) == v for k, v in H3_SELECTOR.items())]
        years = [int(r["year"]) for r in selected]
        if len(selected) != 8 or set(years) != set(range(2017, 2025)) or len(set(years)) != 8:
            raise ValueError("Require exactly one declared 27-key/equal-item/equal-day row for each year 2017–2024")
        annual = {int(r["year"]): {k: Decimal(r[k]) for k in ("key_price", "candidate_index", "ratio")}
                  for r in selected}
        if any(not v.is_finite() or v <= 0 for row in annual.values() for v in row.values()):
            raise ValueError("H3 prices, indices and ratios must be positive and finite")
        ratio_ok = all(abs(r["key_price"] / r["candidate_index"] - r["ratio"]) <= Decimal("1e-10")
                       for r in annual.values())
        results = [claim("H3 ratio arithmetic", "PASS" if ratio_ok else "MISMATCH",
                         "key_price / candidate_index within 1e-10", ratio_ok, scope)]
        for year in (2020, 2023, 2024):
            target = targets[f"price_{year}"]
            results.append(rounded_claim(f"H3 {year} annual key price", target, annual[year]["key_price"], 2, scope))
        pre = [annual[y] for y in (2017, 2018)]
        post = [annual[y] for y in range(2020, 2025)]
        for name, target, actual, places in [
            ("H3 2017–2018 minimum annual key price", targets["price_2017_2018_min"], min(r["key_price"] for r in pre), 2),
            ("H3 2017–2018 maximum annual key price", targets["price_2017_2018_max"], max(r["key_price"] for r in pre), 2),
            ("H3 2017–2018 minimum annual ratio", targets["ratio_2017_2018_min"], min(r["ratio"] for r in pre), 1),
            ("H3 2017–2018 maximum annual ratio", targets["ratio_2017_2018_max"], max(r["ratio"] for r in pre), 1),
            ("H3 2020–2024 minimum annual ratio", targets["ratio_2020_2024_min"], min(r["ratio"] for r in post), 1),
            ("H3 2020–2024 maximum annual ratio", targets["ratio_2020_2024_max"], max(r["ratio"] for r in post), 1),
        ]:
            results.append(rounded_claim(name, target, actual, places, scope))
        return results
    except (OSError, ValueError, KeyError, TypeError, InvalidOperation) as exc:
        return [claim("H3 declared-recipe evidence", "NOT_VERIFIED", scope=scope, note=str(exc))]


def check_corpus(result_path: Path):
    scope = "All raw item histories with full-sample mean price >USD10; no S1b arm or 30-day filter"
    try:
        record = json.loads(result_path.read_text())
        if record.get("definition") != CORPUS_DEFINITION:
            raise ValueError("Corpus result definition does not match the recovered corpus-wide method")
        if record.get("source_archive_sha256") != RAW_SHA256:
            raise ValueError("Corpus result lacks the required raw-snapshot identity")
        if record.get("generator_sha256") != CORPUS_SOURCE_SHA256:
            raise ValueError("Corpus result does not identify the recovered corpus-wide generator")
        rel = record.get("result_log")
        if not isinstance(rel, str) or Path(rel).is_absolute():
            raise ValueError("Provide a relative path to the actual retained verification log")
        log = (result_path.parent / rel).resolve()
        if not log.is_relative_to(result_path.parent.resolve()):
            raise ValueError("Result log must be inside the result-record folder")
        if digest(log) != record.get("result_log_sha256"):
            raise ValueError("Corpus result log is absent or its hash does not match")
        text = decode_text(log)
        # The leading 25,432 is the original script's CLAIM label. Read only FOUND.
        values = re.findall(r"^25,432 day-over-day spikes >100%\s+([\d,]+)\s*$", text, re.M)
        if len(values) != 1 or "SECTION 4.1.1 VERIFICATION" not in text:
            raise ValueError("Exactly one actual FOUND count in the corpus verification log is required")
        found = int(values[0].replace(",", ""))
        if type(record.get("count")) is not int or record["count"] != found:
            raise ValueError("Result-record count does not agree with its actual log")
        return [claim("Corpus-wide >100% daily spike count", "PASS" if found == 25432 else "MISMATCH",
            25432, found, scope,
            "Parsed retained corpus output with declared source identities; no fresh raw-data replication")]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return [claim("Corpus-wide >100% daily spike count", "NOT_VERIFIED", 25432, None, scope,
            f"Actual corpus-wide result evidence is required. {exc}")]


def evaluate(root: Path = ROOT, run: Path | None = None, corpus_result: Path | None = None,
             data_dir: Path | None = None, manuscript: Path | None = None):
    claims = []
    try:
        provenance, integrity = check_provenance(root, data_dir=data_dir, run=run)
        claims.append(integrity)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        provenance = {}
        claims.append(claim("Retained-source integrity", "NOT_VERIFIED", note=str(exc)))
    if run is None:
        paths = {"h3": evidence_path(root, "evidence/h3_index_construction.csv", data_dir),
                 "s1b_summary": evidence_path(root, "evidence/historical_s1b_results.txt", data_dir),
                 "s1b_spikes": evidence_path(root, "evidence/historical_s1b_spikes.csv", data_dir),
                 "historical_names": evidence_path(root, "evidence/historical_raw_filenames.json", data_dir)}
        corpus_result = corpus_result or ((data_dir / "data/corpus_spike_result.json")
                                          if data_dir is not None else root / "evidence/corpus_spike_result.json")
        mode = "retained_evidence_comparison"
    else:
        paths = {"h3": run / "tables/h3_index_construction_sensitivity.csv",
                 "s1b_summary": run / "historical/s1b_cache_old_file_set/s1b_results.txt",
                 "s1b_spikes": run / "historical/s1b_cache_old_file_set/s1b_spikes.csv",
                 "historical_names": run / "inputs/historical_raw_filenames.json"}
        corpus_result = corpus_result or run / "tables/corpus_spike_result.json"
        mode = "comparison_of_provided_full_run_outputs"
        try:
            receipt = json.loads((run / "inputs/download_manifest.json").read_text())
            ok = receipt.get("fresh_extraction") is True and receipt.get("sha256") == RAW_SHA256
            claims.append(claim("Provided-run raw-input identity", "PASS" if ok else "MISMATCH",
                RAW_SHA256, receipt.get("sha256"), "Existing run receipt; this comparator performs no extraction"))
        except (OSError, ValueError, TypeError) as exc:
            claims.append(claim("Provided-run raw-input identity", "NOT_VERIFIED", note=str(exc)))
    claims.extend(check_s1b(paths["s1b_summary"], paths["s1b_spikes"], paths["historical_names"]))
    manuscript = manuscript or root.parent / "revision1_reference/COSE_Manuscript_Clean_19Nov2026.docx"
    document = {"path": str(manuscript), "identity_matches_approved": False}
    try:
        document["sha256"] = digest(manuscript)
        document["approved_sha256"] = provenance["manuscript"]["sha256"]
        document["identity_matches_approved"] = document["sha256"] == document["approved_sha256"]
        document["h3_targets_read_from_docx"] = read_manuscript_h3_targets(manuscript)
        claims.extend(check_h3(paths["h3"], document["h3_targets_read_from_docx"]))
    except (OSError, ValueError, KeyError, TypeError, ET.ParseError, zipfile.BadZipFile) as exc:
        claims.append(claim("H3 manuscript statement", "NOT_VERIFIED", note=str(exc)))
    claims.extend(check_corpus(corpus_result))
    counted = Counter(c["status"] for c in claims)
    counts = {key: counted[key] for key in ("PASS", "MISMATCH", "NOT_VERIFIED")}
    h3 = [row for row in claims if row["claim"].startswith("H3 ")]
    h3_match = len(h3) == 10 and all(row["status"] == "PASS" for row in h3)
    ok = all(c["status"] == "PASS" for c in claims) and document["identity_matches_approved"]
    identities = {k: {"path": str(p), "sha256": digest(p) if p.is_file() else None}
                  for k, p in {**paths, "corpus_result": corpus_result}.items()}
    return {"schema_version": 1, "status": "PASS" if ok else "FAIL",
        "checked_utc": datetime.now(timezone.utc).isoformat(), "mode": mode,
        "historical_claims_agreement": "MATCH" if ok else "NOT_ESTABLISHED",
        "historical_h3": "MATCH_TO_RETAINED_CALCULATION" if h3_match and document["identity_matches_approved"] else "NOT_ESTABLISHED",
        "manuscript_identity": document,
        "full_manuscript_reproduction": "NOT_ESTABLISHED", "counts": counts,
        "claims": claims, "input_identities": identities, "source_provenance": provenance,
        "source_data_or_manuscript_modified_by_comparator": False,
        "scope": "Defined corpus/S1b/H3 historical claims only. H2 and reviewer-requested Appendix A checks are separate.",
        "excluded_from_claim_comparison": [
            "S1b restricted-arm total versus corpus-wide total",
            "Complete-snapshot S1b sensitivity rate versus historical-file-set 2.75",
            "30-key substring and pooled-unit H3 alternatives",
        ],
        "limits": ["No raw-data refit or new simulation", "No claim that missing corpus evidence is wrong",
                   "Retained provenance and hashes identify evidence; they do not establish independent replication"]}


def write_reports(report, destination: Path, legacy_csv: bool = False):
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    fields = ["claim", "status", "expected", "actual", "scope", "note"]
    csv_path = destination.parent / "REVISION1_CLAIM_COMPARISON.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(report["claims"])
    if legacy_csv:
        # Existing launcher checks this filename. Contents are the corrected Revision 1 comparison.
        (destination.parent / "V48_PROSE_CLAIM_COMPARISON.csv").write_bytes(csv_path.read_bytes())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group()
    inputs.add_argument("--run", type=Path, help="Existing full-run output directory; compatible with the previous comparator CLI")
    inputs.add_argument("--data-dir", type=Path, help="Extracted COSE_Revision1_Ty_Reproducibility_Data folder")
    parser.add_argument("--corpus-result", type=Path, help="Actual corpus result JSON with matching method, source hashes and verification log")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--manuscript", type=Path, help="Clean Revision 1 DOCX; defaults to the bundled approved reference")
    args = parser.parse_args(argv)
    run = args.run.resolve() if args.run else None
    destination = args.report or ((run / "comparison") if run else ROOT / "validation_reports") / "HISTORICAL_CLAIMS_REPORT.json"
    report = evaluate(run=run, corpus_result=args.corpus_result,
                      data_dir=args.data_dir.resolve() if args.data_dir else None,
                      manuscript=args.manuscript.resolve() if args.manuscript else None)
    write_reports(report, destination, legacy_csv=run is not None)
    print(f"{report['status']}: {report['counts']}. Historical manuscript agreement: {report['historical_claims_agreement']}.")
    print(f"Report: {destination}")
    print("H2 checks are separate; full manuscript reproduction is not established by this comparator.")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
