"""Independent consistency checks for the current result workbooks."""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parent


def rows(path: Path, sheet: str):
    wb = load_workbook(path, read_only=True, data_only=True)
    try:
        return list(wb[sheet].iter_rows(values_only=True))
    finally:
        wb.close()


def check_plan(path: Path, json_path: Path, adjusted: bool = False) -> dict:
    data = json.loads(json_path.read_text(encoding="utf-8"))
    records = data["records"]
    values = rows(path, "调整购电量" if adjusted else "计划购电量")
    body = values[1:]
    expected = len(records)
    dates = [r[0] for r in body if r and r[0] is not None]
    total_col = 145 if not adjusted else 145
    fee_col = 146
    json_total = float(data["summary"]["total_cost"])
    sheet_total = sum(float(r[fee_col]) for r in body if r[fee_col] is not None)
    return {
        "rows": len(body),
        "date_rows": len(dates),
        "expected_rows": expected,
        "header_first_interval": values[0][1],
        "header_last_interval": values[0][144],
        "json_total_cost": json_total,
        "sheet_total_cost": sheet_total,
        "total_cost_error": abs(json_total - sheet_total),
        "pass": len(body) == expected and values[0][1] == "0:00-0:10" and values[0][144] == "23:50-24:00" and abs(json_total - sheet_total) < 1e-4,
    }


def main() -> None:
    checks = {
        "result1": {
            "rows": len(rows(ROOT / "result1.xlsx", "计划购电量")) - 1,
            "header_first_interval": rows(ROOT / "result1.xlsx", "计划购电量")[1][0],
            "header_last_interval": rows(ROOT / "result1.xlsx", "计划购电量")[-1][0],
        },
        "result2": check_plan(ROOT / "result2.xlsx", ROOT / "q2_rebuild_data.json"),
        "result3": check_plan(ROOT / "result3.xlsx", ROOT / "q3_rebuild_data.json", True),
        "result4_2": check_plan(ROOT / "result4-2.xlsx", ROOT / "q4_2_rebuild_data.json"),
        "result4_3": check_plan(ROOT / "result4-3.xlsx", ROOT / "q4_3_rebuild_data.json", True),
    }
    checks["result1"]["pass"] = checks["result1"]["rows"] == 144 and checks["result1"]["header_first_interval"] == "0:00-0:10" and checks["result1"]["header_last_interval"] == "23:50-0:00+1"
    result = {"status": "PASS" if all(v["pass"] for v in checks.values()) else "FAIL", "checks": checks}
    (ROOT / "artifact_audit.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
