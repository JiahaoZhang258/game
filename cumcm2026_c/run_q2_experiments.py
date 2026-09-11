"""Run non-official Q2 sensitivity and algorithm experiments.

The official result files are not touched. All parameter choices are evaluated
on the frozen February-December period after the January warm-up.
"""
from __future__ import annotations

import json
from dataclasses import asdict, replace
from datetime import date
from pathlib import Path

from solve_q2 import Parameters, WARMUP_PARAMETERS, simulate


ROOT = Path(__file__).resolve().parent
REPORT_START = date(2025, 2, 1)
REPORT_END = date(2025, 12, 31)
BASE_PARAMETERS = Parameters(alpha=0.80, error_window=7, reserve_ratio=0.05, terminal_value=0.30, terminal_soc_target=None)


def run_case(name: str, parameters: Parameters, **kwargs) -> dict:
    parameters = replace(parameters, terminal_soc_target=None)
    _, summary = simulate(
        parameters,
        report_start=REPORT_START,
        report_end=REPORT_END,
        warmup_parameters=WARMUP_PARAMETERS,
        forecast_variant="official",
        **kwargs,
    )
    return {
        "name": name,
        "parameters": asdict(parameters),
        "options": kwargs,
        "summary": summary,
    }


def run_january_validation(name: str, parameters: Parameters, **kwargs) -> dict:
    parameters = replace(parameters, terminal_soc_target=None)
    _, summary = simulate(
        parameters,
        report_start=date(2025, 1, 22),
        report_end=date(2025, 1, 31),
        warmup_parameters=WARMUP_PARAMETERS,
        forecast_variant="official",
        **kwargs,
    )
    return {
        "name": name,
        "parameters": asdict(parameters),
        "options": kwargs,
        "summary": summary,
    }


def run_rolling_fold(
    selection_start: date,
    selection_end: date,
    test_start: date,
    test_end: date,
) -> dict:
    """Select the quantile method on a past block, then evaluate it later.

    Every case uses the same fixed-parameter physical warm-up before the
    block. This isolates the method choice and prevents a candidate's test
    result from changing the initial state of another candidate.
    """
    methods = {
        "ordinary_quantile": {},
        "recent_weighted_quantile_decay_0.50": {"recent_decay": 0.50},
        "recent_weighted_quantile_decay_0.75": {"recent_decay": 0.75},
        "recent_weighted_quantile_decay_0.90": {"recent_decay": 0.90},
    }
    selection_cases = []
    for name, options in methods.items():
        _, summary = simulate(
            BASE_PARAMETERS,
            report_start=selection_start,
            report_end=selection_end,
            warmup_parameters=WARMUP_PARAMETERS,
            forecast_variant="official",
            **options,
        )
        selection_cases.append({
            "name": name,
            "options": options,
            "summary": summary,
        })
    selected = min(
        selection_cases,
        key=lambda row: (
            row["summary"]["total_cost"],
            row["summary"]["emergency_kwh"],
            row["summary"]["emergency_days"],
        ),
    )
    test_cases = []
    for name, options in methods.items():
        _, summary = simulate(
            BASE_PARAMETERS,
            report_start=test_start,
            report_end=test_end,
            warmup_parameters=WARMUP_PARAMETERS,
            forecast_variant="official",
            **options,
        )
        test_cases.append({
            "name": name,
            "options": options,
            "summary": summary,
        })
    selected_test = next(row for row in test_cases if row["name"] == selected["name"])
    official_test = next(row for row in test_cases if row["name"] == "ordinary_quantile")
    return {
        "selection_period": f"{selection_start.isoformat()} to {selection_end.isoformat()}",
        "test_period": f"{test_start.isoformat()} to {test_end.isoformat()}",
        "selected_method": selected["name"],
        "selection_cases": selection_cases,
        "test_cases": test_cases,
        "selected_test": selected_test,
        "official_test": official_test,
        "selected_minus_official_cost": (
            selected_test["summary"]["total_cost"] - official_test["summary"]["total_cost"]
        ),
    }


def main() -> None:
    cases = []
    for window in (4, 7, 14, 28):
        cases.append(run_case(
            f"ordinary_quantile_window_{window}",
            Parameters(alpha=0.80, error_window=window, reserve_ratio=0.05, terminal_value=0.30),
        ))
    for decay in (0.50, 0.75, 0.90):
        cases.append(run_case(
            f"recent_weighted_quantile_decay_{decay:.2f}",
            Parameters(alpha=0.80, error_window=7, reserve_ratio=0.05, terminal_value=0.30),
            recent_decay=decay,
        ))
    validation_cases = []
    for decay in (None, 0.50, 0.75, 0.90):
        kwargs = {} if decay is None else {"recent_decay": decay}
        validation_cases.append(run_january_validation(
            "ordinary_quantile" if decay is None else f"recent_weighted_quantile_decay_{decay:.2f}",
            Parameters(alpha=0.80, error_window=7, reserve_ratio=0.05, terminal_value=0.30),
            **kwargs,
        ))
    rolling_folds = [
        run_rolling_fold(date(2025, 1, 22), date(2025, 1, 31), date(2025, 2, 1), date(2025, 2, 28)),
        run_rolling_fold(date(2025, 2, 1), date(2025, 2, 28), date(2025, 3, 1), date(2025, 3, 31)),
        run_rolling_fold(date(2025, 3, 1), date(2025, 3, 31), date(2025, 4, 1), date(2025, 4, 30)),
        run_rolling_fold(date(2025, 4, 1), date(2025, 4, 30), date(2025, 5, 1), date(2025, 5, 31)),
    ]
    payload = {
        "evaluation_period": f"{REPORT_START.isoformat()} to {REPORT_END.isoformat()}",
        "warmup": "Historical experiment: fixed original warmup and original weighted forecasts; not the new official policy",
        "official_case": "ordinary_quantile_window_7",
        "cases": cases,
        "january_validation": validation_cases,
        "rolling_validation": {
            "description": "Each method is selected on a completed past block and evaluated on the following block; test blocks are never used for selection.",
            "base_parameters": asdict(BASE_PARAMETERS),
            "folds": rolling_folds,
        },
    }
    output = ROOT / "q2_algorithm_experiments.json"
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "output": str(output),
        "cases": [
            {"name": c["name"], "total_cost": c["summary"]["total_cost"], "emergency_kwh": c["summary"]["emergency_kwh"]}
            for c in cases
        ],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
