"""Fair ablation of the Q2 ideas borrowed from the comparison solution.

The official result files are not touched. Every annual run starts from the
same physical-January SOC and uses only observations before the decision day.
"""
from __future__ import annotations

import csv
import json
from dataclasses import asdict, replace
from datetime import date
from pathlib import Path

import numpy as np
from scipy.optimize import linprog
from scipy.sparse import coo_matrix

import solve_q2 as q2


ROOT = Path(__file__).resolve().parent
REPORT_START = q2.REPORT_START
REPORT_END = q2.REPORT_END


def plan_day_with_terminal(
    price: np.ndarray,
    demand: np.ndarray,
    initial_soc: float,
    parameters: q2.Parameters,
    terminal_soc: float,
) -> dict[str, np.ndarray]:
    """Experimental copy of plan_day with an explicit terminal SOC equality."""
    n = 5 * q2.T
    q, charge, discharge, soc, surplus = 0, q2.T, 2 * q2.T, 3 * q2.T, 4 * q2.T
    objective = np.zeros(n)
    objective[q:q2.T] = price
    objective[charge:charge + q2.T] = q2.REGULARIZER
    objective[discharge:discharge + q2.T] = q2.REGULARIZER
    bounds = [(0.0, None)] * q2.T
    bounds += [(0.0, q2.P_MAX * q2.DT)] * q2.T
    bounds += [(0.0, q2.P_MAX * q2.DT)] * q2.T
    bounds += [(q2.SOC_MIN, q2.SOC_MAX)] * q2.T
    bounds += [(0.0, None)] * q2.T
    rows, cols, values, rhs = [], [], [], []
    def add(row: int, col: int, value: float) -> None:
        rows.append(row); cols.append(col); values.append(value)
    row = 0
    for t in range(q2.T):
        add(row, q + t, 1.0); add(row, discharge + t, 1.0)
        add(row, charge + t, -1.0); add(row, surplus + t, -1.0)
        rhs.append(float(demand[t])); row += 1
    for t in range(q2.T):
        add(row, soc + t, 1.0); add(row, charge + t, -q2.ETA)
        add(row, discharge + t, 1.0 / q2.ETA)
        if t: add(row, soc + t - 1, -1.0); rhs.append(0.0)
        else: rhs.append(float(initial_soc))
        row += 1
    add(row, soc + q2.T - 1, 1.0); rhs.append(float(terminal_soc)); row += 1
    result = linprog(
        objective,
        A_eq=coo_matrix((values, (rows, cols)), shape=(row, n)).tocsr(),
        b_eq=np.asarray(rhs), bounds=bounds, method="highs",
    )
    if not result.success:
        raise RuntimeError(f"terminal-SOC LP failed: {result.message}")
    x = result.x
    return {
        "purchase_kw": np.maximum(x[q:q2.T], 0.0),
        "charge_kw": np.maximum(x[charge:charge + q2.T], 0.0),
        "discharge_kw": np.maximum(x[discharge:discharge + q2.T], 0.0),
        "soc": x[soc:soc + q2.T],
        "surplus_kw": np.maximum(x[surplus:surplus + q2.T], 0.0),
    }


def borrowed_forecast_day(
    day_index: int,
    dates: list[date],
    load: np.ndarray,
    pv: np.ndarray,
    typical_load: np.ndarray,
    typical_pv: np.ndarray,
    parameters: q2.Parameters,
    use_borrowed_load: bool,
    use_borrowed_pv: bool,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Forecast one day from completed rows only."""
    def basic(j: int) -> tuple[np.ndarray, np.ndarray]:
        if j == 0:
            return typical_load.copy(), typical_pv.copy()

        if use_borrowed_load:
            history = [load[i] for i in range(j) if dates[i].weekday() == dates[j].weekday()][-4:]
            load_hat = q2._smooth(np.mean(history, axis=0) if history else np.mean(load[:j], axis=0))
        else:
            history = [load[i] for i in range(j) if dates[i].weekday() == dates[j].weekday()][-4:]
            load_hat = q2._smooth(q2._weighted_mean(history) if history else np.mean(load[:j], axis=0))

        if use_borrowed_pv:
            history_pv = list(pv[max(0, j - 21) : j])
            if len(history_pv) <= 1:
                pv_hat = history_pv[0].copy() if history_pv else typical_pv.copy()
            else:
                y = np.asarray(history_pv, dtype=float)
                x = np.arange(len(y), dtype=float)
                centered = x - x.mean()
                slope = centered @ y / (centered @ centered)
                pv_hat = np.maximum(y.mean(axis=0) + slope * (len(y) - x.mean()), 0.0)
        else:
            history_pv = list(pv[max(0, j - 4) : j])
            pv_hat = q2._weighted_mean(history_pv) if history_pv else typical_pv.copy()
        return load_hat, pv_hat

    load_f, pv_f = basic(day_index)
    if day_index == 0:
        return load_f, pv_f, np.empty((0, q2.T))

    residuals = []
    start = max(1, day_index - parameters.error_window)
    for j in range(start, day_index):
        previous_load, previous_pv = basic(j)
        actual = (load[j] - pv[j]) * q2.DT
        predicted = (previous_load - previous_pv) * q2.DT
        residuals.append(actual - predicted)
    return load_f, pv_f, np.asarray(residuals, dtype=float)


def run_variant(
    dates: list[date],
    load: np.ndarray,
    pv: np.ndarray,
    price: np.ndarray,
    initial_soc: float,
    parameters: q2.Parameters,
    use_borrowed_load: bool,
    use_borrowed_pv: bool,
    terminal_soc: float | None = None,
) -> tuple[dict, dict]:
    parameters = replace(parameters, terminal_soc_target=terminal_soc)
    att1 = q2.load_attachment1(q2.DATA / "附件1.xlsx")
    typical_load = np.asarray(att1["load"], dtype=float)
    typical_pv = np.asarray(att1["pv"], dtype=float)
    state = float(initial_soc)
    records = []
    for day_index, day in enumerate(dates):
        if day < REPORT_START:
            continue
        load_f, pv_f, residuals = borrowed_forecast_day(
            day_index, dates, load, pv, typical_load, typical_pv, parameters,
            use_borrowed_load, use_borrowed_pv,
        )
        demand = q2.design_demand(load_f, pv_f, residuals, parameters.alpha)
        plan = q2.plan_day(price, demand, state, parameters) if terminal_soc is None else plan_day_with_terminal(price, demand, state, parameters, terminal_soc)
        execution = q2.execute_day(
            price, load[day_index], pv[day_index], plan["purchase_kw"],
            plan["soc"], state, parameters.reserve_ratio,
        )
        records.append({
            "date": day,
            "soc0": state,
            "soc24": float(execution["soc_trace"][-1]),
            "purchase_kwh": plan["purchase_kw"],
            "charge_kwh": execution["charge_kwh"],
            "discharge_kwh": execution["discharge_kwh"],
            "emergency_kwh": execution["emergency_kwh"],
            "surplus_kwh": execution["surplus_kwh"],
            "soc_trace": execution["soc_trace"],
            "load_kwh": load[day_index] * q2.DT,
            "pv_kwh": pv[day_index] * q2.DT,
        })
        state = float(execution["soc_trace"][-1])

    bundle = {"price": price, "records": records}
    summary = q2.summarize(bundle)
    summary.update({
        "state_at_report_start": float(initial_soc),
        "period_start": REPORT_START.isoformat(),
        "period_end": REPORT_END.isoformat(),
        "period_end_soc": float(records[-1]["soc24"]),
    })
    q2.validate(bundle, summary)
    return bundle, summary


def main() -> None:
    dates, load, pv = q2.load_attachment2()
    att1 = q2.load_attachment1(q2.DATA / "附件1.xlsx")
    price = np.asarray(att1["price"], dtype=float)

    # One physical January trajectory is shared by every annual comparison.
    warmup_params = q2.WARMUP_PARAMETERS
    warmup_bundle, warmup_summary = q2.simulate(
        warmup_params,
        report_start=q2.JANUARY_START,
        report_end=q2.JANUARY_END,
        warmup_parameters=warmup_params,
        forecast_variant="official",
    )
    common_initial_soc = float(warmup_summary["period_end_soc"])

    variants = [
        ("official_current", False, False, q2.Parameters(alpha=0.80, error_window=7, reserve_ratio=0.05, terminal_value=0.30)),
        ("borrowed_pv_only", False, True, q2.Parameters(alpha=0.80, error_window=7, reserve_ratio=0.05, terminal_value=0.30)),
        ("borrowed_load_pv", True, True, q2.Parameters(alpha=0.80, error_window=7, reserve_ratio=0.05, terminal_value=0.30)),
        ("borrowed_load_pv_risk", True, True, q2.Parameters(alpha=0.825, error_window=7, reserve_ratio=0.625, terminal_value=0.30), None),
        ("borrowed_load_pv_risk_terminal2400", True, True, q2.Parameters(alpha=0.825, error_window=7, reserve_ratio=0.625, terminal_value=0.30), 2400.0),
    ]
    rows = []
    details = {}
    normalized_variants = []
    for item in variants:
        if len(item) == 4:
            normalized_variants.append((*item, None))
        else:
            normalized_variants.append(item)
    for name, use_load, use_pv, params, terminal_soc in normalized_variants:
        bundle, summary = run_variant(
            dates, load, pv, price, common_initial_soc, params, use_load, use_pv, terminal_soc,
        )
        row = {
            "variant": name,
            **asdict(params),
            "borrowed_load": use_load,
            "borrowed_pv": use_pv,
            "terminal_soc": terminal_soc,
            **summary,
        }
        rows.append(row)
        details[name] = {"summary": summary, "records": [
            {"date": r["date"].isoformat(), "soc0": r["soc0"], "soc24": r["soc24"]}
            for r in bundle["records"]
        ]}

    out_json = ROOT / "q2_borrowed_algorithm_experiment.json"
    out_csv = ROOT / "q2_borrowed_algorithm_experiment.csv"
    payload = {
        "common_january_warmup_end_soc": common_initial_soc,
        "warmup_summary": warmup_summary,
        "information_rule": "all forecast variants use only rows with index < decision day; annual evaluation starts 2025-02-01",
        "status": "Historical ablation; official_current names the pre-migration policy, not the new default",
        "variants": details,
    }
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=float), encoding="utf-8")
    fields = list(rows[0])
    with out_csv.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    for row in rows:
        print(json.dumps({k: row[k] for k in ["variant", "total_cost", "emergency_kwh", "plan_cost", "emergency_cost", "period_end_soc"]}, ensure_ascii=False))
    print(f"common_january_warmup_end_soc={common_initial_soc:.6f}")
    print(f"wrote {out_json}")
    print(f"wrote {out_csv}")


if __name__ == "__main__":
    main()
