"""CUMCM 2026 C题 Q1：典型日计划购电 LP。

约定（已确认）：
- 时间戳 = 区间起点（附件1 的 0:10 对应 0:10-0:20，与 result1 模板对齐）
- 充、放效率各 90%；5000 kW 限制在交流侧
- 0:00 SOC 自由，仅要求与 24:00 循环相等
- 不允许售电，允许弃光，购电功率无上限
"""
from __future__ import annotations

import json
import math
import zipfile
import xml.etree.ElementTree as ET
from collections import defaultdict
from copy import copy
from pathlib import Path

import numpy as np
from openpyxl import load_workbook
from scipy.optimize import linprog

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
ROOT = Path("/home/jason/projects/game/cumcm2026_c")
DATA = Path("/home/jason/下载/CUMCM2026Problems/C题/附件")
TEMPLATE = DATA / "附件5" / "result1.xlsx"

ETA = 0.9
DT = 1.0 / 6.0  # h
P_MAX = 5000.0  # kW, AC side
SOC_MIN = 1200.0
SOC_MAX = 10800.0
T = 144


def _col_row(ref: str) -> tuple[str, int]:
    i = 0
    while i < len(ref) and ref[i].isalpha():
        i += 1
    return ref[:i], int(ref[i:])


def _shared_strings(z: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in z.namelist():
        return []
    root = ET.fromstring(z.read("xl/sharedStrings.xml"))
    out = []
    for si in root.findall("m:si", NS):
        out.append("".join(t.text or "" for t in si.findall(".//m:t", NS)))
    return out


def load_attachment1(path: Path) -> dict:
    z = zipfile.ZipFile(path)
    ss = _shared_strings(z)
    sheet = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
    rows: dict[int, dict[str, str | None]] = defaultdict(dict)
    for c in sheet.findall(".//m:c", NS):
        ref = c.attrib.get("r")
        if not ref:
            continue
        col, row = _col_row(ref)
        t = c.attrib.get("t")
        v = c.find("m:v", NS)
        val = v.text if v is not None else None
        if t == "s" and val is not None:
            val = ss[int(val)]
        rows[row][col] = val
    z.close()

    minutes, price, load, pv, labels = [], [], [], [], []
    for r in range(2, max(rows) + 1):
        raw = rows[r]["A"]
        try:
            mins = int(round(float(raw) * 24 * 60))
        except (TypeError, ValueError):
            s = str(raw).replace("+1", "")
            if s in {"0:00", "00:00"}:
                mins = 24 * 60
            else:
                hh, mm = s.split(":")
                mins = int(hh) * 60 + int(mm)
                if "+1" in str(raw):
                    mins += 24 * 60
        minutes.append(mins)
        price.append(float(rows[r]["B"]))
        load.append(float(rows[r]["C"]))
        pv.append(float(rows[r]["D"]))
        labels.append(str(raw) if not str(raw).replace(".", "", 1).replace("E-", "").replace("E+", "").replace("e-", "").replace("e+", "").isdigit() and "E" not in str(raw).upper() else _mins_to_label(mins))
    return {
        "minutes": np.array(minutes, dtype=int),
        "price": np.array(price, dtype=float),
        "load": np.array(load, dtype=float),
        "pv": np.array(pv, dtype=float),
        "labels": labels,
    }


def _mins_to_label(mins: int) -> str:
    if mins >= 24 * 60:
        extra = mins - 24 * 60
        h, m = divmod(extra, 60)
        if extra == 0:
            return "0:00+1"
        return f"{h}:{m:02d}+1"
    h, m = divmod(mins, 60)
    return f"{h}:{m:02d}"


def interval_label(start_min: int) -> str:
    return f"{_mins_to_label(start_min)}-{_mins_to_label(start_min + 10)}"


def solve_q1(data: dict) -> dict:
    price = data["price"]
    load = data["load"]
    pv = data["pv"]
    assert len(price) == T

    # variables: buy, ch, dis, curt, E_end, E0
    n = 5 * T + 1
    buy, ch, dis, curt, eend, e0 = 0, T, 2 * T, 3 * T, 4 * T, 5 * T

    c = np.zeros(n)
    c[buy : buy + T] = price * DT

    bounds = [(0, None)] * T  # buy
    bounds += [(0, P_MAX)] * T  # ch
    bounds += [(0, P_MAX)] * T  # dis
    bounds += [(0, None)] * T  # curt
    bounds += [(SOC_MIN, SOC_MAX)] * T  # E_end
    bounds += [(SOC_MIN, SOC_MAX)]  # E0

    A_eq = []
    b_eq = []

    # power balance: buy - ch + dis - curt = load - pv
    for t in range(T):
        row = np.zeros(n)
        row[buy + t] = 1.0
        row[ch + t] = -1.0
        row[dis + t] = 1.0
        row[curt + t] = -1.0
        A_eq.append(row)
        b_eq.append(load[t] - pv[t])

    # SOC dynamics
    for t in range(T):
        row = np.zeros(n)
        row[eend + t] = 1.0
        if t == 0:
            row[e0] = -1.0
        else:
            row[eend + t - 1] = -1.0
        row[ch + t] = -ETA * DT
        row[dis + t] = DT / ETA
        A_eq.append(row)
        b_eq.append(0.0)

    # cyclic: E_end[T-1] = E0
    row = np.zeros(n)
    row[eend + T - 1] = 1.0
    row[e0] = -1.0
    A_eq.append(row)
    b_eq.append(0.0)

    res = linprog(
        c,
        A_eq=np.asarray(A_eq),
        b_eq=np.asarray(b_eq),
        bounds=bounds,
        method="highs",
        options={"presolve": True},
    )
    if not res.success:
        raise RuntimeError(f"LP failed: {res.message}")

    x = res.x
    sol = {
        "buy_kw": x[buy : buy + T],
        "ch_kw": x[ch : ch + T],
        "dis_kw": x[dis : dis + T],
        "curt_kw": x[curt : curt + T],
        "soc_end": x[eend : eend + T],
        "soc0": float(x[e0]),
        "cost": float(res.fun),
        "status": res.message,
    }
    return sol


def four_hour_bins(minutes: np.ndarray) -> list[np.ndarray]:
    """Convention A: bin by start minute; 24:00 maps into 0:00-4:00 of the cycle."""
    bins = [[] for _ in range(6)]
    for i, m in enumerate(minutes):
        bins[(int(m) % (24 * 60)) // 240].append(i)
    return [np.array(ix, dtype=int) for ix in bins]


def summarize(data: dict, sol: dict) -> dict:
    minutes = data["minutes"]
    buy_kwh = sol["buy_kw"] * DT
    ch_kwh = sol["ch_kw"] * DT
    dis_kwh = sol["dis_kw"] * DT
    curt_kwh = sol["curt_kw"] * DT
    cost = float(np.dot(data["price"], buy_kwh))

    # specified 10-min slots (start timestamps)
    want = {
        "10:00-10:10": 10 * 60,
        "12:00-12:10": 12 * 60,
        "14:00-14:10": 14 * 60,
        "16:00-16:10": 16 * 60,
        "18:00-18:10": 18 * 60,
        "20:00-20:10": 20 * 60,
    }
    table1 = {}
    for name, m in want.items():
        idx = int(np.where(minutes == m)[0][0])
        table1[name] = float(buy_kwh[idx])

    windows = ["0:00-4:00", "4:00-8:00", "8:00-12:00", "12:00-16:00", "16:00-20:00", "20:00-24:00"]
    bins = four_hour_bins(minutes)
    table2 = {}
    for name, ix in zip(windows, bins):
        table2[name] = {
            "charge": float(ch_kwh[ix].sum()),
            "discharge": float(dis_kwh[ix].sum()),
            "n": int(len(ix)),
        }

    # diagnostics
    both = np.minimum(sol["ch_kw"], sol["dis_kw"])
    soc = np.concatenate([[sol["soc0"]], sol["soc_end"]])
    baseline = float(np.dot(data["price"], np.maximum(data["load"] - data["pv"], 0) * DT))

    return {
        "table1": table1,
        "table1_total_buy_kwh": float(buy_kwh.sum()),
        "table1_total_cost": cost,
        "table2": table2,
        "soc0": sol["soc0"],
        "soc24": float(sol["soc_end"][-1]),
        "diagnostics": {
            "pv_kwh": float(data["pv"].sum() * DT),
            "load_kwh": float(data["load"].sum() * DT),
            "curt_kwh": float(curt_kwh.sum()),
            "ch_kwh": float(ch_kwh.sum()),
            "dis_kwh": float(dis_kwh.sum()),
            "simultaneous_kw_max": float(both.max()),
            "soc_min": float(soc.min()),
            "soc_max": float(soc.max()),
            "baseline_no_storage_cost": baseline,
            "savings_vs_baseline": baseline - cost,
        },
        "buy_kwh": buy_kwh.tolist(),
        "ch_kwh": ch_kwh.tolist(),
        "dis_kwh": dis_kwh.tolist(),
        "curt_kwh": curt_kwh.tolist(),
        "soc_end": sol["soc_end"].tolist(),
        "interval_labels": [interval_label(int(m)) for m in minutes],
    }


def write_result1(summary: dict, out_path: Path) -> None:
    wb = load_workbook(TEMPLATE)
    ws = wb["计划购电量"]
    # template rows 2..145 correspond to 144 intervals
    labels = summary["interval_labels"]
    buys = summary["buy_kwh"]
    for i, (lab, val) in enumerate(zip(labels, buys)):
        row = i + 2
        # keep template label; warn if mismatch
        tpl = ws.cell(row, 1).value
        if tpl and str(tpl).replace(" ", "") != lab.replace(" ", ""):
            # still fill by row order (convention A)
            pass
        ws.cell(row, 2, round(val, 4))

    ws2 = wb["充放电量"]
    windows = ["0:00-4:00", "4:00-8:00", "8:00-12:00", "12:00-16:00", "16:00-20:00", "20:00-24:00"]
    for i, name in enumerate(windows):
        row = i + 2
        ws2.cell(row, 2, round(summary["table2"][name]["charge"], 4))
        ws2.cell(row, 3, round(summary["table2"][name]["discharge"], 4))
    ws2.cell(2, 5, round(summary["soc0"], 4))
    ws2.cell(3, 5, round(summary["soc24"], 4))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out_path)


def main() -> None:
    data = load_attachment1(DATA / "附件1.xlsx")
    sol = solve_q1(data)
    summary = summarize(data, sol)
    out_xlsx = ROOT / "result1.xlsx"
    write_result1(summary, out_xlsx)

    slim = {k: v for k, v in summary.items() if k not in {"buy_kwh", "ch_kwh", "dis_kwh", "curt_kwh", "soc_end", "interval_labels"}}
    slim["result_file"] = str(out_xlsx)
    (ROOT / "q1_summary.json").write_text(json.dumps(slim, ensure_ascii=False, indent=2), encoding="utf-8")

    # also dump full series for later
    np.savez(
        ROOT / "q1_trajectory.npz",
        minutes=data["minutes"],
        price=data["price"],
        load=data["load"],
        pv=data["pv"],
        buy_kw=sol["buy_kw"],
        ch_kw=sol["ch_kw"],
        dis_kw=sol["dis_kw"],
        curt_kw=sol["curt_kw"],
        soc_end=sol["soc_end"],
        soc0=np.array([sol["soc0"]]),
    )

    print("LP cost (yuan):", round(summary["table1_total_cost"], 4))
    print("Total buy kWh:", round(summary["table1_total_buy_kwh"], 4))
    print("SOC0 / SOC24:", round(summary["soc0"], 4), round(summary["soc24"], 4))
    print("Table1:", {k: round(v, 4) for k, v in summary["table1"].items()})
    print("Table2:")
    for k, v in summary["table2"].items():
        print(" ", k, "ch", round(v["charge"], 4), "dis", round(v["discharge"], 4), "n", v["n"])
    print("Diagnostics:", {k: (round(v, 4) if isinstance(v, float) else v) for k, v in summary["diagnostics"].items()})
    print("Wrote", out_xlsx)


if __name__ == "__main__":
    main()
