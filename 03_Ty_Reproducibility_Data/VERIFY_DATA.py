#!/usr/bin/env python3
"""Check this derived-data packet's integrity, types and recorded scope."""

from collections import Counter
import csv
from datetime import date
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path, PurePosixPath
import sys


def typed(value, kind):
    nullable = kind.endswith('?')
    kind = kind.rstrip('?')
    if value == '' and nullable:
        return
    if kind == 'integer':
        number = Decimal(value)
        if not number.is_finite() or number != number.to_integral_value():
            raise ValueError('expected integer')
    elif kind == 'number':
        if not Decimal(value).is_finite():
            raise ValueError('expected finite number')
    elif kind == 'number_or_positive_infinity':
        number = Decimal(value)
        if not (number.is_finite() or number == Decimal('Infinity')):
            raise ValueError('expected finite number or retained positive infinity')
    elif kind == 'boolean':
        if value not in ('True', 'False'):
            raise ValueError('expected True or False')
    elif kind == 'date':
        date.fromisoformat(value)
    elif kind != 'text':
        raise ValueError('unknown schema type')


def main(root):
    failures = []
    checked = 0
    try:
        manifest = json.loads((root / 'PACKAGE_MANIFEST.json').read_text(encoding='utf-8'))
        seen = set()
        for entry in manifest['files']:
            relative = entry['path']
            parts = PurePosixPath(relative)
            if parts.is_absolute() or '..' in parts.parts or relative in seen:
                raise ValueError('Unsafe or repeated manifest path: ' + relative)
            seen.add(relative)
            file = root.joinpath(*parts.parts)
            if not file.is_file():
                failures.append('Missing file: ' + relative)
                continue
            data = file.read_bytes()
            if len(data) != entry['bytes']:
                failures.append('Size mismatch: ' + relative)
            if hashlib.sha256(data).hexdigest() != entry['sha256']:
                failures.append('SHA-256 mismatch: ' + relative)
            checked += 1
    except (OSError, ValueError, KeyError, TypeError) as exc:
        failures.append('Manifest: ' + str(exc))

    datasets = {}
    try:
        schemas = json.loads((root / 'DATA_SCHEMA.json').read_text(encoding='utf-8'))
        for spec in schemas['csv_files']:
            relative = spec['path']
            with (root / relative).open(encoding='utf-8-sig', newline='') as handle:
                reader = csv.DictReader(handle)
                fields = reader.fieldnames or []
                if fields != spec['columns']:
                    raise ValueError('Column mismatch: ' + relative)
                rows = list(reader)
            if len(rows) != spec['rows']:
                failures.append('Row-count mismatch: ' + relative)
            for i, row in enumerate(rows, 2):
                if None in row or any(value is None for value in row.values()):
                    failures.append('Malformed CSV row: ' + relative + ':' + str(i))
                    break
                try:
                    for field, kind in spec['types'].items():
                        typed(row[field], kind)
                except (ValueError, InvalidOperation, KeyError) as exc:
                    failures.append('Type mismatch: ' + relative + ':' + str(i) + ': ' + str(exc))
                    break
            datasets[relative] = rows

        classifications = datasets['data/ITEM_CLASSIFICATIONS.csv']
        if len({row['item_id'] for row in classifications}) != 22495:
            failures.append('Item classification IDs are not 22,495 unique IDs')
        arms = Counter(row['whole_word_arm'] for row in classifications)
        if arms != {'substitute': 597, 'control': 1580, 'key': 27, 'excluded': 20291}:
            failures.append('Classification-arm counts differ from retained inventory')

        containers = datasets['data/container_definitions.csv']
        flags = sum(row['key_dependent_case'] == 'True' for row in containers)
        if len(containers) != 597 or flags != 29:
            failures.append('Candidate-definition table must have 597 rows and 29 key-dependent container flags')
        candidates = {row['item_id']: row['item'] for row in classifications if row['whole_word_arm'] == 'substitute'}
        if {row['item_id']: row['item'] for row in containers} != candidates:
            failures.append('Candidate-definition IDs/names differ from the classification inventory')

        summaries = datasets['data/H2/PROFILE_SUMMARIES.csv']
        curves = datasets['data/H2/RECOVERY_CURVES.csv']
        result_ids = {row['result_id'] for row in summaries}
        expected_profiles = {'step', 'ramp7', 'ramp21', 'delay7', 'delay14', 'delay28', 'distributed', 'heterogeneous'}
        if len(result_ids) != 32 or {row['scenario'] for row in summaries} != expected_profiles:
            failures.append('H2 summary scope differs from the 32 current profile results')
        if Counter(row['result_id'] for row in curves) != Counter({key: 20 for key in result_ids}):
            failures.append('Recovery curves must contain 20 recorded doses for each of the 32 results')
        for row in summaries + curves:
            if (row['cohort'], row['model'], row['scale'], row['implementation'], row['calibration']) != (
                    'full_archive', 'TWFE', 'eventual', 'Dell_empirical_coefficient_noise', 'frozen150_centered'):
                failures.append('H2 scope mismatch')
                break

        h3 = datasets['data/H3/INDEX_CONSTRUCTION_27KEYS.csv']
        if {row['year'] for row in h3} != {str(year) for year in range(2017, 2025)}:
            failures.append('H3 annual coverage differs from 2017–2024')
        if any((row['scope'], row['keys'], row['recipe']) != (
                'full_zip', 'whole_word_27keys', 'equal_item_daily_mean_then_equal_days') for row in h3):
            failures.append('H3 recipe scope mismatch')

        historical_files = json.loads((root / 'data/S1b/historical_raw_filenames.json').read_text(encoding='utf-8'))
        if not isinstance(historical_files, list) or len(historical_files) != 22420:
            failures.append('Historical filename inventory differs from the recorded 22,420 names')
        spikes = datasets['data/S1b/historical_spikes.csv']
        primary = Counter(row['arm'] for row in spikes if row['mean_price_gt10'] == 'True')
        if primary != {'fungible': 1508, 'nonfungible': 18292}:
            failures.append('Historical classified-sample primary spike counts differ from the retained records')
    except (OSError, ValueError, KeyError, TypeError, csv.Error) as exc:
        failures.append('Dataset structure: ' + str(exc))

    if failures:
        for failure in failures:
            print('FAIL: ' + failure)
        print('FAILED: ' + str(len(failures)) + ' integrity/structure issue(s).')
        return 1
    print('INTEGRITY PASS: ' + str(checked) + ' listed files match their recorded SHA-256 hashes and sizes.')
    print('STRUCTURE PASS: CSV types, recorded row counts and specified dataset scopes agree.')
    print('597 candidate-definition rows contain 29 key-dependent container exclusion flags.')
    print('STATUS: Retained-data integrity and structure checks are complete.')
    print('For H3 display agreement and the remaining corpus-wide claim, use the companion manuscript comparison.')
    return 0


if __name__ == '__main__':
    sys.exit(main(Path(__file__).resolve().parent))
