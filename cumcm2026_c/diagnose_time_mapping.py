"""Read-only audit of source timestamps against current paper indices."""
from __future__ import annotations

import json
from datetime import datetime, time
from pathlib import Path

from openpyxl import load_workbook

from build_paper_draft import SLOTS


ROOT = Path(__file__).resolve().parent
DATA = Path('/home/jason/下载/CUMCM2026Problems/C题/附件')


def minutes(value) -> int:
    if isinstance(value, time):
        return value.hour * 60 + value.minute
    if isinstance(value, (float, int)):
        return round(value * 1440)
    value = str(value)
    hh, mm = value.removesuffix('+1').split(':')
    return int(hh) * 60 + int(mm) + (1440 if value.endswith('+1') else 0)


def diagnose(data_dir: Path = DATA) -> dict:
    wb = load_workbook(data_dir / '附件2.xlsx', read_only=True, data_only=True)
    try:
        rows = wb['小区负载'].values
        header = next(rows)
        dates = [row[0].date() if isinstance(row[0], datetime) else row[0]
                 for row in rows if row[0] is not None]
    finally:
        wb.close()
    source_minutes = [minutes(v) for v in header[1:]]
    if source_minutes != list(range(10, 1441, 10)):
        raise ValueError('Unexpected source time axis; inspect the input before mapping it')
    if len(dates) != 365 or any((b - a).days != 1 for a, b in zip(dates, dates[1:])):
        raise ValueError('Source dates are incomplete or not consecutive')

    checks = []
    for index, label in SLOTS:
        start = minutes(label.split('-')[0])
        endpoint = start + 10
        source_index = source_minutes.index(endpoint)
        checks.append({
            'interval': label,
            'paper_array_index': index,
            'source_endpoint_index': source_index,
            'matches_endpoint_interpretation': index == source_index,
        })
    return {
        'status': 'PASS' if all(c['matches_endpoint_interpretation'] for c in checks) else 'FAIL',
        'source_date_count': len(dates),
        'source_first_date': dates[0].isoformat(),
        'source_last_date': dates[-1].isoformat(),
        'source_first_minute': source_minutes[0],
        'source_last_minute': source_minutes[-1],
        'specified_slots': checks,
        'template_mapping': 'source endpoint labels map directly to the same-position natural-day intervals; no cross-day shift or imputation',
        'scope': 'This checks endpoint labels, specified-slot indices, and source completeness only.',
    }


def main() -> None:
    result = diagnose()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result['status'] == 'PASS' else 1)


if __name__ == '__main__':
    main()
