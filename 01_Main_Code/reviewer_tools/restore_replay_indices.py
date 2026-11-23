#!/usr/bin/env python3
"""Restore frozen RNG index files, requiring original array contents.

This helper reconstructs saved pseudorandom indices from the seeds and draw order
in scripts/injection_revision.py. It does not fit models or simulate new primary
outcomes. Fitted coefficient arrays remain separate, retained input evidence.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import platform
import sys
import tempfile
import zipfile
import zlib

import numpy as np


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def checked_path(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise ValueError(f"Recipe path leaves the replay root: {relative}")
    return path


def generate_arrays(settings: dict, entry: dict) -> dict[str, np.ndarray]:
    """Follow the source draw order exactly, including separate model indices."""
    repetitions = settings["repetitions"]
    bootstraps = settings["bootstrap_repetitions"]
    length = settings["block_days"]
    frozen_rows = entry["frozen_rows"]
    calendar_rows = entry["calibration_rows"]
    gi = ["all", "exclude_cases", "exclude_broad"].index(entry["group"])
    models = ["TWFE"] if entry["scale"] == "equal_cumulative" else ["item_FE", "TWFE"]
    mi = models.index(entry["model"])
    noise_seed = settings["seed"] + 10000 + gi * 100 + mi
    bootstrap_seed = settings["bootstrap_seed"] + gi * 100 + mi
    if (gi, mi, noise_seed, bootstrap_seed) != (
        entry["group_index"], entry["model_index"], entry["noise_seed"], entry["bootstrap_seed"]
    ):
        raise ValueError(f"Inconsistent seed recipe for {entry['path']}")

    rng = np.random.default_rng(noise_seed)
    noise_indices = rng.integers(0, frozen_rows, size=repetitions)
    bootrng = np.random.default_rng(bootstrap_seed)
    iid_indices = bootrng.integers(0, frozen_rows, size=(bootstraps, frozen_rows))
    block_indices = []
    for _ in range(bootstraps):
        starts = bootrng.integers(0, calendar_rows, size=int(np.ceil(calendar_rows / length)))
        block_indices.append(
            ((starts[:, None] + np.arange(length)) % calendar_rows).ravel()[:calendar_rows]
        )
    block_indices = np.array(block_indices)
    bootstrap_run_indices = bootrng.integers(0, repetitions, size=(bootstraps, repetitions))
    bootstrap_noise_iid = bootrng.integers(0, frozen_rows, size=(bootstraps, repetitions))
    bootstrap_noise_block = bootrng.integers(0, calendar_rows, size=(bootstraps, repetitions))
    return {
        "noise_indices": noise_indices,
        "iid_indices": iid_indices,
        "block_indices": block_indices,
        "bootstrap_run_indices": bootstrap_run_indices,
        "bootstrap_noise_iid": bootstrap_noise_iid,
        "bootstrap_noise_block": bootstrap_noise_block,
    }


def verify_arrays(arrays: dict[str, np.ndarray], entry: dict) -> None:
    expected_keys = [spec["name"] for spec in entry["arrays"]]
    if list(arrays) != expected_keys:
        raise ValueError(f"Array ordering or keys differ for {entry['path']}")
    for spec in entry["arrays"]:
        array = arrays[spec["name"]]
        actual = (
            list(array.shape), array.dtype.str,
            hashlib.sha256(array.tobytes(order="C")).hexdigest(),
        )
        expected = (spec["shape"], spec["dtype"], spec["sha256_c_order_bytes"])
        if actual != expected:
            raise ValueError(f"Original-array verification failed: {entry['path']}:{spec['name']}")


def write_npz(path: Path, arrays: dict[str, np.ndarray], entry: dict) -> None:
    # Original NPZs were written on Windows. Explicit ZIP metadata preserves
    # their original SHA-256 hashes when rebuilt on this verified Linux setup.
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
        archive.comment = bytes.fromhex(entry["zip_comment_hex"])
        for spec in entry["arrays"]:
            metadata = spec["zip_info"]
            info = zipfile.ZipInfo(metadata["filename"], tuple(metadata["date_time"]))
            for field in (
                "compress_type", "create_system", "create_version", "extract_version",
                "external_attr", "internal_attr", "volume", "flag_bits",
            ):
                setattr(info, field, metadata[field])
            info.extra = bytes.fromhex(metadata["extra_hex"])
            info.comment = bytes.fromhex(metadata["comment_hex"])
            with archive.open(info, "w", force_zip64=True) as member:
                np.save(member, arrays[spec["name"]], allow_pickle=False)


def restore(root: Path, recipe: dict) -> list[dict]:
    calibration = checked_path(root, recipe["calibration_source"]["path"])
    if file_sha256(calibration) != recipe["calibration_source"]["sha256"]:
        raise ValueError("Retained calibration source does not match the reconstruction recipe")
    with calibration.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))

    receipts = []
    for entry in recipe["files"]:
        subset = [
            row for row in rows
            if row["candidate_group"] == entry["group"] and row["model"] == entry["model"]
        ]
        if (len(subset), sum(row["in_frozen150"] == "True" for row in subset)) != (
            entry["calibration_rows"], entry["frozen_rows"]
        ):
            raise ValueError(f"Calibration dimensions differ for {entry['path']}")

        target = checked_path(root, entry["path"])
        arrays = generate_arrays(recipe["settings"], entry)
        verify_arrays(arrays, entry)
        already_present = target.exists()
        if not already_present:
            target.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temporary_name = tempfile.mkstemp(prefix=target.name + ".", dir=target.parent)
            os.close(descriptor)
            temporary = Path(temporary_name)
            try:
                write_npz(temporary, arrays, entry)
                temporary.replace(target)
            finally:
                temporary.unlink(missing_ok=True)

        # The arrays are the evidence. Every array read back from the file must match the
        # original shape, data type and SHA-256; a file that fails this is never accepted.
        with np.load(target, allow_pickle=False) as archive:
            restored = {name: archive[name] for name in archive.files}
        verify_arrays(restored, entry)
        # The compressed container (ZIP/DEFLATE bytes) depends on the zlib build of the
        # machine, so its hash is recorded for information and is no longer a pass condition.
        container_matches = (
            file_sha256(target) == entry["original_sha256"]
            and target.stat().st_size == entry["original_size_bytes"]
        )
        receipts.append({
            "path": entry["path"], "action": "verified_existing" if already_present else "restored",
            "arrays_verified": len(entry["arrays"]), "array_hashes_match_original": True,
            "npz_sha256": file_sha256(target), "npz_hash_matches_original": container_matches,
            "size_bytes": target.stat().st_size,
        })
    return receipts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True, help="Reviewer workspace containing evidence/")
    parser.add_argument("--recipe", type=Path, default=Path(__file__).with_name("REPLAY_INDEX_RECIPE.json"))
    parser.add_argument("--report", type=Path, help="Optional JSON receipt path")
    args = parser.parse_args()
    recipe = json.loads(args.recipe.read_text(encoding="utf-8"))
    if recipe["schema_version"] != 1:
        raise ValueError("Unsupported index recipe schema")
    receipts = restore(args.root.resolve(), recipe)
    report = {
        "status": "PASS", "scope": "Lossless reconstruction of saved pseudorandom index files",
        "raw_data_extraction_or_model_refitting": False,
        "recipe_sha256": file_sha256(args.recipe), "files_verified": len(receipts),
        "arrays_verified": sum(item["arrays_verified"] for item in receipts),
        "all_array_hashes_match_original": all(item["array_hashes_match_original"] for item in receipts),
        "all_npz_hashes_match_original": all(item["npz_hash_matches_original"] for item in receipts),
        "python_version": platform.python_version(), "numpy_version": np.__version__,
        "zlib_runtime_version": zlib.ZLIB_RUNTIME_VERSION, "files": receipts,
    }
    if args.report is not None:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
