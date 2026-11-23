#!/usr/bin/env python3
"""Verify the included R2.1 records using only Python's standard library."""

import csv
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import sys
import xml.etree.ElementTree as ET
import zipfile


PINNED_PLANS = (
    ("originals_for_verification/KeyBan_Natural_Experiment_PreRegistration.docx",
     "6463c6cdf91b8c207458dbb0f37eb1c862145534d0c4d0f44351e87753cd0320",
     "2026-07-17T22:40:01Z"),
    ("originals_for_verification/Laundering_Signature_Prespecification.docx",
     "452d4379c5ead4f959c496430ab7fe231fba6b6532727ca88d1c3a89fa96f142",
     "2026-07-17T22:25:09Z"),
    ("public_copies/S1_KeyBan_Analysis_Plan_Public_Copy.docx",
     "44e1a004a473f43178ec54597b1800f020c90de04649874a219f1f7c68f3f22a",
     "2026-11-13T22:30:48Z"),
    ("public_copies/S2_Signature_Specification_Public_Copy.docx",
     "b4fb52f6c62904ab630f1d8bb10c70bbeb68721d4e2ba12c81fda5810e779c79",
     "2026-11-13T22:30:48Z"),
)


def verify(root):
    failures = []
    checked_files = 0
    checked_plans = 0
    mapping_rows = 0

    try:
        manifest = json.loads((root / "PACKAGE_MANIFEST.json").read_text(encoding="utf-8"))
        entries = manifest["files"]
        seen = set()
        for entry in entries:
            relative = entry["path"]
            path_parts = PurePosixPath(relative)
            if path_parts.is_absolute() or ".." in path_parts.parts or relative in seen:
                raise ValueError("Unsafe or repeated manifest path: " + relative)
            seen.add(relative)
            path = root.joinpath(*path_parts.parts)
            if not path.is_file():
                failures.append("Missing file: " + relative)
                continue
            data = path.read_bytes()
            if len(data) != entry["bytes"]:
                failures.append("Size mismatch: " + relative)
            if hashlib.sha256(data).hexdigest() != entry["sha256"]:
                failures.append("SHA-256 mismatch: " + relative)
            checked_files += 1
    except (OSError, ValueError, KeyError, TypeError) as exc:
        failures.append("Manifest verification: " + str(exc))

    for relative, expected_hash, expected_time in PINNED_PLANS:
        try:
            data = (root / relative).read_bytes()
            if hashlib.sha256(data).hexdigest() != expected_hash:
                failures.append("Recorded source identity mismatch: " + relative)
            with zipfile.ZipFile(io.BytesIO(data)) as document:
                if document.testzip() is not None:
                    raise ValueError("DOCX CRC failure")
                core = ET.fromstring(document.read("docProps/core.xml"))
                ET.fromstring(document.read("word/document.xml"))
            for field in ("created", "modified"):
                value = core.findtext("{http://purl.org/dc/terms/}" + field)
                if value != expected_time:
                    failures.append("Embedded " + field + " mismatch: " + relative)
            checked_plans += 1
        except (OSError, ValueError, KeyError, ET.ParseError, zipfile.BadZipFile) as exc:
            failures.append("Plan verification for " + relative + ": " + str(exc))

    try:
        record = json.loads((root / "current_mapping/Appendix_A1_source.json").read_text(encoding="utf-8"))
        with (root / "current_mapping/Appendix_Table_A1.csv").open(newline="", encoding="utf-8-sig") as handle:
            actual = list(csv.reader(handle))
        expected = [record["columns"]] + record["rows"]
        if actual != expected:
            failures.append("Current Appendix A1 CSV differs from the recorded source extract")
        if [row[0] for row in record["rows"]] != ["H1", "H2", "H3", "S1b"]:
            failures.append("Current Appendix A1 test list differs from the four source rows")
        mapping_rows = len(record["rows"])
    except (OSError, ValueError, KeyError, TypeError, csv.Error) as exc:
        failures.append("Current Appendix A1 verification: " + str(exc))

    if failures:
        for failure in failures:
            print("FAIL: " + failure)
        print("FAILED: " + str(len(failures)) + " verification issue(s).")
        return 1

    print("PASS: " + str(checked_files) + " listed files match their SHA-256 hashes and sizes.")
    print("PASS: " + str(checked_plans) + " plan DOCX files match the recorded identities and embedded UTC dates; ZIP/XML checks passed.")
    print("PASS: " + str(mapping_rows) + " current Appendix A1 rows match the included source extract.")
    print("Scope: file identity, embedded metadata and the supplied mapping only.")
    print("Public registration, public deposit, first execution and scientific results are not established by this check.")
    return 0


if __name__ == "__main__":
    sys.exit(verify(Path(__file__).resolve().parent))
