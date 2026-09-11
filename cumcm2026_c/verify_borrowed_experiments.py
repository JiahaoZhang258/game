"""Reproduce borrowed policies and audit them without modifying official outputs."""
from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import sys
import tempfile
import zipfile
from pathlib import Path

import numpy as np

import run_borrowed_q2_experiment as experiment
import solve_q2 as q2
import solve_q34 as q34

ROOT = Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def q3_physics(m, records, load, pv, price):
    assert [r['day'] for r in records] == list(range(31, 365))
    converted = []
    for r in records:
        costs = m.totals([r], price)
        assert np.min(r['surplus']) >= -1e-8
        assert np.max(r['charge'] * r['emergency']) < 1e-8
        converted.append({
            'soc0': r['initial_soc'], 'soc24': float(r['soc'][-1]),
            'adjusted_purchase_kwh': r['a'], 'charge_kwh': r['charge'],
            'discharge_kwh': r['discharge'], 'emergency_kwh': r['emergency'],
            'surplus_kwh': r['surplus'], 'soc_trace': r['soc'],
            'load_kwh': load[r['day']] / 6, 'pv_kwh': pv[r['day']] / 6,
            'plan_cost': costs['planned_cost'], 'emergency_cost': costs['emergency_cost'],
            'adjustment_cost': costs['upward_adjustment_cost'] + costs['downward_penalty'],
            'total_cost': costs['total_cost'],
        })
    return q34.validate({'records': converted}, m.totals(records, price))


def main():
    official_paths = list(ROOT.glob('result*.xlsx')) + [
        ROOT / name for name in ('q2_summary.json', 'q3_summary.json',
                                'q2_rebuild_data.json', 'q3_rebuild_data.json', '论文初稿.md')
    ]
    before_hashes = {p.name: digest(p) for p in official_paths}
    dates, load, pv = q2.load_attachment2()
    typical = q2.load_attachment1(q2.DATA / '附件1.xlsx')
    price = np.asarray(typical['price'])
    _, january = q2.simulate(q2.WARMUP_PARAMETERS, report_start=q2.JANUARY_START,
                             report_end=q2.JANUARY_END, forecast_variant="official")
    common = january['period_end_soc']
    params = q2.Parameters(alpha=.825, error_window=7, reserve_ratio=.625, terminal_value=.30)
    bundle, summary = experiment.run_variant(dates, load, pv, price, common, params, True, True, 2400.)
    physical = q2.validate(bundle, summary)
    recorded = json.loads((ROOT / 'q2_borrowed_algorithm_experiment.json').read_text())
    expected = recorded['variants']['borrowed_load_pv_risk_terminal2400']['summary']['total_cost']
    assert abs(summary['total_cost'] - expected) < 1e-6
    q2_tests = []
    for day, cut in [(31, 36), (78, 72), (265, 108)]:
        changed_load, changed_pv = load.copy(), pv.copy()
        changed_load[day:] += 1500
        changed_pv[day:] *= .2
        args = (typical['load'], typical['pv'], params, True, True)
        original = experiment.borrowed_forecast_day(day, dates, load, pv, *args)
        modified = experiment.borrowed_forecast_day(day, dates, changed_load, changed_pv, *args)
        for a, b in zip(original, modified):
            np.testing.assert_array_equal(a, b)
        record = bundle['records'][day - 31]
        demand = q2.design_demand(*original, params.alpha)
        plan = experiment.plan_day_with_terminal(price, demand, record['soc0'], params, 2400.)
        assert abs(plan['soc'][-1] - 2400.) < 1e-8
        altered = load[day].copy()
        altered[cut:] += 1500
        executed = q2.execute_day(price, altered, pv[day], plan['purchase_kw'], plan['soc'], record['soc0'], params.reserve_ratio)
        for key in ('charge_kwh', 'discharge_kwh', 'emergency_kwh', 'soc_trace'):
            np.testing.assert_array_equal(executed[key][:cut], record[key][:cut])
        q2_tests.append({'day': dates[day].isoformat(), 'cut': cut, 'status': 'PASS'})
    np.savez_compressed(ROOT / 'q2_borrowed_joint_trajectory.npz', **{
        key: np.asarray([r[key] for r in bundle['records']])
        for key in ('purchase_kwh', 'charge_kwh', 'discharge_kwh', 'emergency_kwh', 'surplus_kwh', 'soc_trace', 'soc0')
    })

    # Execute only the inspected solvers, never their CLI/export entry points.
    source_hashes = {}
    with tempfile.TemporaryDirectory(prefix='borrowed-q3-') as directory:
        root = Path(directory)
        for archive_name, member in [('问题3.zip', '问题3/solve_q3.py'),
                                     ('问题2最终版.zip', '问题2最终版/solve_q2.py')]:
            archive = Path('/home/jason/下载') / archive_name
            source_hashes[archive_name] = digest(archive)
            with zipfile.ZipFile(archive) as z:
                z.extract(member, root)
        path = root / '问题3/solve_q3.py'
        spec = importlib.util.spec_from_file_location('borrowed_q3_audit', path)
        m = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = m
        spec.loader.exec_module(m)
        m.ATT = q2.DATA
        official_bundle, official_summary = q34.simulate_q3_or_q4(False)
        current_q3 = json.loads((ROOT / 'q3_summary.json').read_text())['summary']
        assert abs(official_summary['total_cost'] - current_q3['total_cost']) < 1e-6
        assert official_bundle['records'][0]['soc0'] == common
        m.INITIAL = common
        forecasts = m.read_forecasts()
        cache = m.ForecastCache(load, pv, forecasts, .5)
        masks = [(), (6,), (12,), (18,), (6, 12), (6, 18), (12, 18), (6, 12, 18)]
        rows, validations = [], {}
        for mask in masks:
            config = m.Config(blend=.5, alpha=.7, rho=.625, updates=mask)
            records, decisions, diagnostics = m.simulate(load, pv, forecasts, price, range(31, 365), config, cache, record_updates=True)
            name = ','.join(map(str, mask)) or 'none'
            result = m.totals(records, price)
            validations[name] = q3_physics(m, records, load, pv, price)
            for log in decisions:
                r = records[log['day'] - 31]
                start = log['hour'] * 6
                assert abs(log['initial_soc'] - r['soc'][start - 1]) < 1e-7
                assert abs(log['committed_addition'] - (r['a'][start:start+36] - r['q'][start:start+36]).sum()) < 1e-7
            rows.append({'updates': name, **{k: float(result[k]) for k in (
                'total_cost', 'planned_cost', 'upward_adjustment_cost', 'emergency_cost', 'emergency_kwh', 'final_soc')}})
            print('Q3', name, rows[-1]['total_cost'], flush=True)
        selected = records
        np.savez_compressed(ROOT / 'q3_borrowed_joint_trajectory.npz', **{
            key: np.asarray([r[key] for r in selected])
            for key in ('q', 'a', 'charge', 'discharge', 'emergency', 'surplus', 'soc', 'initial_soc')
        })
        q3_tests = []
        for day, hour in [(31, 6), (78, 12), (265, 18)]:
            cut = hour * 6
            m.INITIAL = selected[day - 31]['initial_soc']
            base = m.simulate(load, pv, forecasts, price, [day], config, cache)[0][0]
            changed_load, changed_pv = load.copy(), pv.copy()
            changed_load[day, cut:] += 1000
            changed_pv[day, cut:] *= .2
            altered = m.ForecastCache(changed_load[:day+1], changed_pv[:day+1], forecasts[:day+1], .5)
            changed = m.simulate(changed_load, changed_pv, forecasts, price, [day], config, altered)[0][0]
            np.testing.assert_array_equal(base['q'], changed['q'])
            np.testing.assert_array_equal(base['a'][:cut+36], changed['a'][:cut+36])
            np.testing.assert_array_equal(base['soc'][:cut], changed['soc'][:cut])
            new_forecasts = forecasts[:day+1].copy()
            new_forecasts[day, m.HOURS.index(hour):] *= .2
            altered = m.ForecastCache(load[:day+1], pv[:day+1], new_forecasts, .5)
            changed = m.simulate(load, pv, new_forecasts, price, [day], config, altered)[0][0]
            np.testing.assert_array_equal(base['q'], changed['q'])
            np.testing.assert_array_equal(base['a'][:cut], changed['a'][:cut])
            np.testing.assert_array_equal(base['soc'][:cut], changed['soc'][:cut])
            q3_tests.append({'day': dates[day].isoformat(), 'issue_hour': hour, 'status': 'PASS'})

    with (ROOT / 'q3_borrowed_update_ablation.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    after_hashes = {p.name: digest(p) for p in official_paths}
    assert before_hashes == after_hashes
    report = {
        'status': 'PASS', 'common_initial_soc': common, 'official_files_unchanged': True,
        'official_sha256': after_hashes, 'source_archive_sha256': source_hashes,
        'q2': {'summary': summary, 'validation': physical, 'perturbations': q2_tests},
        'q3': {'official_summary': official_summary, 'update_ablation': rows,
               'validation': validations, 'perturbations': q3_tests},
        'limits': 'Reference reproduction after official migration. Configurations were chosen following retrospective comparisons, not an independent held-out test. This script does not edit official outputs. Tests cover specified boundaries, not a formal causality proof.',
    }
    (ROOT / 'borrowed_experiment_validation.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    print('Borrowed experiment validation PASS', flush=True)


if __name__ == '__main__':
    main()
