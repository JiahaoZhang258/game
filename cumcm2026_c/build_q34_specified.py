from __future__ import annotations

import json
from pathlib import Path

from build_paper_draft import WINDOWS, segments

ROOT = Path(__file__).resolve().parent
DAYS = ["2025-03-20", "2025-06-21", "2025-09-23", "2025-12-21"]


def data(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def table(data_file, day):
    rec = next(r for r in data_file["records"] if r["date"] == day)
    lines = [f"### {day}", "", "| 指标 | 数值 |", "|---|---:|", f"| 原计划购电量 | {sum(rec['purchase_kwh']):.6f} |"]
    if "adjusted_purchase_kwh" in rec:
        lines += [f"| 调整后购电量 | {sum(rec['adjusted_purchase_kwh']):.6f} |", f"| 增加量 | {sum(rec['adjustment_up_kwh']):.6f} |", f"| 减少量 | {sum(rec['adjustment_down_kwh']):.6f} |", f"| 计划购电费 | {rec['plan_cost']:.6f} |", f"| 调整费用 | {rec['adjustment_cost']:.6f} |"]
    else:
        lines += [f"| 计划购电费 | {rec['plan_cost']:.6f} |"]
    lines += [f"| 紧急购电量 | {sum(rec['emergency_kwh']):.6f} |", f"| 紧急购电费 | {rec['emergency_cost']:.6f} |", f"| 总费用 | {rec['total_cost']:.6f} |", f"| 0:00储电量 | {rec['soc0']:.6f} |", f"| 24:00储电量 | {rec['soc24']:.6f} |", "", "| 紧急购电时间段 | 电量/kWh |", "|---|---:|"]
    ev = segments(rec["emergency_kwh"])
    lines += [f"| {span} | {amount:.6f} |" for span, amount in ev] or ["| 无 | 0 |"]
    lines.append("")
    return lines


def main():
    q3 = data("q3_rebuild_data.json")
    q43 = data("q4_3_rebuild_data.json")
    out = ["# 问题3、问题4指定日期结果（当前版）", "", "问题3使用固定电价，问题4使用附件4实际电价进行事后结算。问题3/4的日前价格预测只使用历史价格，调整只发生在6:00、12:00、18:00。所有电量单位为 kWh，费用单位为元。", "", "## 问题3"]
    for day in DAYS: out += table(q3, day)
    out += ["## 问题4-3", ""]
    for day in DAYS: out += table(q43, day)
    out += ["## 说明", "", "问题4-2指定日期数据位于 result4-2.xlsx；问题3和问题4-3的完整计划、调整计划、储能和紧急购电明细分别位于 result3.xlsx 和 result4-3.xlsx。"]
    (ROOT / "问题3_4指定日期结果_初版.md").write_text("\n".join(out) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
