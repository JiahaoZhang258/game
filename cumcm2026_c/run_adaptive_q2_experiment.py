"""Causal adaptive quantile experiments for Question 2.

Each fold selects one forecasting configuration on a completed historical
block and evaluates that fixed choice on the immediately following block.
The official result files are never modified.
"""
from __future__ import annotations

import json
from dataclasses import asdict, replace
from datetime import date
from pathlib import Path

from solve_q2 import Parameters, WARMUP_PARAMETERS, simulate


ROOT = Path(__file__).resolve().parent
BASE = Parameters(alpha=0.80, error_window=7, reserve_ratio=0.05, terminal_value=0.30, terminal_soc_target=None)
METHODS = [
    {"name": f"ordinary_alpha_{alpha:.2f}_window_{window}", "parameters": Parameters(alpha=alpha, error_window=window, reserve_ratio=0.05, terminal_value=0.30), "options": {}}
    for alpha in (0.70, 0.80, 0.90)
    for window in (4, 7, 14)
]
METHODS += [
    {"name": f"weighted_alpha_{alpha:.2f}_decay_{decay:.2f}", "parameters": Parameters(alpha=alpha, error_window=7, reserve_ratio=0.05, terminal_value=0.30), "options": {"recent_decay": decay}}
    for alpha in (0.70, 0.80, 0.90)
    for decay in (0.75, 0.90)
]


def evaluate(method: dict, start: date, end: date) -> dict:
    parameters = replace(method["parameters"], terminal_soc_target=None)
    _, summary = simulate(
        parameters,
        report_start=start,
        report_end=end,
        warmup_parameters=WARMUP_PARAMETERS,
        forecast_variant="official",
        **method["options"],
    )
    return {
        "name": method["name"],
        "parameters": asdict(parameters),
        "options": method["options"],
        "summary": summary,
    }


def fold(selection_start: date, selection_end: date, test_start: date, test_end: date) -> dict:
    selection = [evaluate(m, selection_start, selection_end) for m in METHODS]
    chosen = min(
        selection,
        key=lambda x: (
            x["summary"]["total_cost"],
            x["summary"]["emergency_kwh"],
            x["summary"]["emergency_days"],
        ),
    )
    test = [evaluate(m, test_start, test_end) for m in METHODS]
    selected_test = next(x for x in test if x["name"] == chosen["name"])
    official_test = next(x for x in test if x["name"] == "ordinary_alpha_0.80_window_7")
    return {
        "selection_period": f"{selection_start.isoformat()} to {selection_end.isoformat()}",
        "test_period": f"{test_start.isoformat()} to {test_end.isoformat()}",
        "selected_method": chosen["name"],
        "selected_parameters": chosen["parameters"],
        "selected_test": selected_test,
        "official_test": official_test,
        "selected_minus_official_cost": selected_test["summary"]["total_cost"] - official_test["summary"]["total_cost"],
        "selection_ranking": sorted(
            [
                {
                    "name": x["name"],
                    "total_cost": x["summary"]["total_cost"],
                    "emergency_kwh": x["summary"]["emergency_kwh"],
                }
                for x in selection
            ],
            key=lambda x: (x["total_cost"], x["emergency_kwh"]),
        )[:5],
        "test_ranking": sorted(
            [
                {
                    "name": x["name"],
                    "total_cost": x["summary"]["total_cost"],
                    "emergency_kwh": x["summary"]["emergency_kwh"],
                }
                for x in test
            ],
            key=lambda x: (x["total_cost"], x["emergency_kwh"]),
        )[:5],
    }


def main() -> None:
    folds = [
        (date(2025, 1, 22), date(2025, 1, 31), date(2025, 2, 1), date(2025, 2, 28)),
        (date(2025, 3, 1), date(2025, 3, 31), date(2025, 4, 1), date(2025, 4, 30)),
        (date(2025, 5, 1), date(2025, 5, 31), date(2025, 6, 1), date(2025, 6, 30)),
        (date(2025, 7, 1), date(2025, 7, 31), date(2025, 8, 1), date(2025, 8, 31)),
        (date(2025, 9, 1), date(2025, 9, 30), date(2025, 10, 1), date(2025, 10, 31)),
        (date(2025, 11, 1), date(2025, 11, 30), date(2025, 12, 1), date(2025, 12, 31)),
    ]
    results = [fold(*periods) for periods in folds]
    payload = {
        "method": "causal rolling adaptive quantile selection",
        "candidate_count": len(METHODS),
        "base_parameters": asdict(BASE),
        "selection_rule": "minimum past-block total cost, then emergency energy and days",
        "folds": results,
        "aggregate_selected_minus_official_cost": sum(x["selected_minus_official_cost"] for x in results),
    }
    output = ROOT / "q2_adaptive_experiment.json"
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "output": str(output),
        "candidate_count": len(METHODS),
        "folds": [
            {
                "selection_period": x["selection_period"],
                "test_period": x["test_period"],
                "selected_method": x["selected_method"],
                "delta_cost": x["selected_minus_official_cost"],
            }
            for x in results
        ],
        "aggregate_delta_cost": payload["aggregate_selected_minus_official_cost"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
