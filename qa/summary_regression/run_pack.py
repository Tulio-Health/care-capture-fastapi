#!/usr/bin/env python3
"""Opt-in mixed regression runner. No app startup, DB or automatic AI calls."""
import argparse
import copy
from contextlib import contextmanager
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import socket
import sys
import time

from reporting import fixture_inventory, write_report
from outcome_assessment import classify_contained_result

from ai_runtime import BudgetExceeded, ConfigurationError, RegressionAI, load_config, redact
from execution_context import ExecutionContext

ROOT = Path(__file__).resolve().parent
RESULTS = ROOT.parent / 'results'
MISSING = object()


def lookup(obj, path):
    for key in path.split('.'):
        if not isinstance(obj, dict) or key not in obj:
            return MISSING
        obj = obj[key]
    return obj


def equal(actual, expected):
    if type(actual) is not type(expected):
        return False
    if isinstance(expected, dict):
        return actual.keys() == expected.keys() and all(equal(actual[k], v) for k, v in expected.items())
    if isinstance(expected, list):
        return len(actual) == len(expected) and all(equal(a, b) for a, b in zip(actual, expected))
    return actual == expected


def matches(actual, op, expected):
    if actual is MISSING:
        return False
    if op == 'eq':
        return equal(actual, expected)
    if op == 'one_of':
        return any(equal(actual, x) for x in expected)
    if op in ('contains', 'not_contains'):
        if not isinstance(actual, (str, list, dict)):
            return False
        found = expected in actual
        return found if op == 'contains' else not found
    if op in ('lte', 'gte'):
        if type(actual) not in (int, float) or type(expected) not in (int, float):
            return False
        return actual <= expected if op == 'lte' else actual >= expected
    raise ValueError('Unknown check operation: ' + op)


@contextmanager
def no_network():
    """Block ordinary Python socket connections, including adapter import side effects.

    This is defense in depth, not an OS sandbox: subprocesses/native clients are prohibited
    by the adapter contract and require an external network-restricted process in CI.
    """
    def denied(*args, **kwargs):
        raise RuntimeError('Network disabled for mocked regression cases.')
    original = socket.socket.connect, socket.socket.connect_ex, socket.create_connection
    socket.socket.connect = denied
    socket.socket.connect_ex = denied
    socket.create_connection = denied
    try:
        yield
    finally:
        socket.socket.connect, socket.socket.connect_ex, socket.create_connection = original


def evaluate(case, observed):
    if not isinstance(observed, dict):
        raise TypeError('Adapter must return an observed JSON object')
    failures = []
    for check in case['expected']:
        actual = lookup(observed, check['path'])
        if not matches(actual, check['op'], check['value']):
            reported = '<MISSING>' if actual is MISSING else actual
            if isinstance(reported, str) and len(reported) > 4000:
                import hashlib
                reported = {'preview': reported[:4000], 'characters': len(reported), 'sha256': hashlib.sha256(reported.encode()).hexdigest(), 'report_truncated': True}
            failures.append({'check': check, 'actual': reported})
    review_pending = bool(case['manual_review']) and observed.get('manual_review_completed') is not True
    return ('FAIL' if failures else 'REVIEW_REQUIRED' if review_pending else 'PASS'), failures


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mode', choices=['mock', 'live', 'mixed'], default='mock')
    p.add_argument('--list', action='store_true', help='List cases only; no key read, imports or calls')
    p.add_argument('--check-config', action='store_true', help='Check live configuration locally without API calls')
    p.add_argument('--adapter', type=Path, default=ROOT / 'application_adapter.py', help='Same fixed-FastAPI adapter for both modes; unwired cases are BLOCKED')
    p.add_argument('--env-file', type=Path, help='Explicit regression-only key/config file; never auto-loads application .env')
    p.add_argument('--live-case', action='append', default=[], help='Limit live calls to these profile IDs while mixed mode still runs all selected mock cases')
    p.add_argument('--case', action='append', default=[], help='Exact case ID; repeat to select several')
    p.add_argument('--repeat', type=int, default=1, help='Repeat each live case (1-10); mocks run once')
    p.add_argument('--execute', action='store_true', help='Explicit execution; live/mixed can incur API charges')
    p.add_argument('--allow-live-model', action='store_true', help=argparse.SUPPRESS)
    args = p.parse_args()
    if args.allow_live_model:
        p.error('Use --mode live or --mode mixed instead of --allow-live-model.')
    if not 1 <= args.repeat <= 10:
        p.error('--repeat must be between 1 and 10.')
    mock = json.loads((ROOT / 'cases.json').read_text())['cases']
    profile = json.loads((ROOT / 'live_profile.json').read_text())
    live_ids = set(profile['case_ids'])
    if args.live_case and (args.mode == 'mock' or set(args.live_case) - live_ids):
        p.error('--live-case requires live/mixed mode and known live-profile case IDs.')
    selected_live_ids = set(args.live_case) if args.live_case else live_ids
    if live_ids - {c['id'] for c in mock}:
        p.error('Live profile contains unknown case IDs.')
    available = [c for c in mock if c['id'] in live_ids] if args.mode == 'live' else mock
    unknown = set(args.case) - {c['id'] for c in available}
    if unknown:
        p.error('Unknown case IDs for selected mode: ' + ', '.join(sorted(unknown)))
    chosen = [c for c in available if not args.case or c['id'] in args.case]
    if args.list:
        for c in chosen:
            print(c['id'] + '  ' + c['title'])
        return 0
    config = None
    if args.check_config:
        if args.mode == 'mock':
            print('Mock mode: no API key needed; network disabled; persistence in memory.')
        else:
            try:
                config = load_config(args.env_file)
            except ConfigurationError as exc:
                p.error(str(exc))
            print('Regression key configured (not displayed). No API call or account-access validation performed.')
            print(f'Model: {config.model}; vision: {config.vision_model}; max attempts: {config.max_calls}')
        return 0
    if not args.execute:
        p.error('No tests run. Execution requires --execute. Use --list or --check-config to inspect locally.')
    tasks = []
    for c in chosen:
        if args.mode in ('mock', 'mixed'):
            tasks.append((c, 'mock'))
        if args.mode in ('live', 'mixed') and c['id'] in selected_live_ids:
            tasks.append((c, 'live'))
    if any(c.get('inject') for c, mode in tasks if mode == 'live'):
        p.error('Live profile cannot contain fault-injection cases; keep those in mock mode.')
    has_live = any(mode == 'live' for _, mode in tasks)
    if has_live:
        try:
            config = load_config(args.env_file)
        except ConfigurationError as exc:
            p.error(str(exc))
    module = None
    if tasks:
        if not args.adapter.is_file():
            p.error('Adapter file does not exist.')
        try:
            with no_network():
                spec = importlib.util.spec_from_file_location('qa_summary_adapter', args.adapter.resolve())
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
        except Exception as exc:
            p.error('Application adapter import failed: ' + type(exc).__name__)
        if getattr(module, 'PERSISTENCE_MODE', None) != 'memory':
            p.error('Adapter must declare PERSISTENCE_MODE="memory". Database access is prohibited.')
        if not callable(getattr(module, 'run_case', None)):
            p.error('Adapter must define run_case(case, fixture_dir, context).')
        required_modes = {mode for _, mode in tasks}
        if not required_modes.issubset(set(getattr(module, 'SUPPORTED_MODES', set()))):
            p.error('Adapter must explicitly support each requested mode; use the updated adapter contract.')
    ai = RegressionAI(config) if config else None
    secret = config.api_key if config else ''
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
    run_dir = RESULTS
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / 'outputs').mkdir(exist_ok=True)
    fixtures = fixture_inventory(ROOT)
    requirements = json.loads((ROOT / 'coverage.json').read_text())['requirements']
    state = 'running'
    rows = []
    statuses = ['PASS', 'SAFELY_REJECTED', 'FAIL', 'BLOCKED', 'REVIEW_REQUIRED', 'ERROR', 'CANCELLED']

    def save():
        counts = {s: sum(r['status'] == s for r in rows) for s in statuses}
        report = {
            'run_id': run_id, 'state': state,
            'updated_at': datetime.now(timezone.utc).isoformat(),
            'planned_executions': sum(args.repeat if mode == 'live' else 1 for _, mode in tasks),
            'pack_case_count': len(mock),
            'not_selected_case_count': len(mock) - len({c['id'] for c, _ in tasks}),
            'unexecuted_case_ids': sorted({c['id'] for c in mock} - {r['id'] for r in rows}),
            'mode': args.mode, 'persistence': 'memory',
            'application_adapter': str(args.adapter.resolve()),
            'scope': 'actual FastAPI pipeline; external persistence in memory; no DB or mobile integration qualification',
            'counts': counts, 'cases': rows, 'fixtures': fixtures, 'requirements': requirements,
            'ai': {'attempts': ai.calls, 'total_tokens': ai.total_tokens, 'events': ai.events,
                   'model': config.model, 'vision_model': config.vision_model,
                   'max_calls': config.max_calls} if ai else None,
        }
        write_report(run_dir, redact(report, secret))
        return counts

    save()
    try:
        for original_case, mode in tasks:
            case = copy.deepcopy(original_case)
            is_live = mode == 'live'
            if is_live:
                # Gold files remain evaluator oracles; never fake model answers in live mode.
                case['config'].pop('vision_response', None)
                case['manual_review'] = list(case.get('manual_review', [])) + [
                    'Review actual FastAPI summary against source facts; AI self-review cannot approve this case.']
            for iteration in range(1, (args.repeat if is_live else 1) + 1):
                row = {'id': case['id'], 'iteration': iteration,
                       'scope': 'application_live' if is_live else 'application_mock',
                       'title': case['title'], 'fixtures': case['fixtures'],
                       'plan_refs': case['plan_refs'], 'config': case['config'],
                       'inject': case['inject'], 'manual_review': case['manual_review']}
                observed = None
                started = time.monotonic()
                rows.append(row)
                try:
                    if not is_live and case['config'].get('mode') == 'real_model_opt_in':
                        raise NotImplementedError('Application live evaluation is not wired.')
                    if any(name not in fixtures or fixtures[name]['integrity'] != 'PASS' for name in case['fixtures']):
                        raise NotImplementedError('Synthetic document missing or failed catalog integrity check')
                    context = ExecutionContext(mode=mode, ai=ai if is_live else None)
                    if is_live:
                        before_calls = ai.calls
                        ai.blocked_reason = None
                        observed = module.run_case(case, ROOT.parent / 'testdata', context)
                        if ai.blocked_reason and not (isinstance(observed, dict) and observed.get('pipeline_output', {}).get('summary')):
                            raise BudgetExceeded('Regression transport budget reached')
                        if ai.calls == before_calls:
                            raise RuntimeError('Live case did not call the injected regression AI client.')
                        if not isinstance(observed, dict) or not isinstance(observed.get('pipeline_output'), dict):
                            raise RuntimeError('Live adapter must return actual pipeline_output for review.')
                    else:
                        with no_network():
                            observed = module.run_case(case, ROOT.parent / 'testdata', context)
                    row['status'], row['failures'] = evaluate(case, observed)
                    if is_live:
                        if not observed['pipeline_output'].get('summary'):
                            row['status'] = 'FAIL'
                            row['failures'].append({'check': {'path': 'pipeline_output.summary', 'op': 'present', 'value': True}, 'actual': None})
                except (NotImplementedError, BudgetExceeded) as exc:
                    row.update(status='BLOCKED', reason='AI budget reached' if isinstance(exc, BudgetExceeded) else str(exc), blocked_category='ai_budget' if isinstance(exc, BudgetExceeded) else 'adapter_or_fixture', budget_reason=ai.blocked_reason if isinstance(exc, BudgetExceeded) else None)
                except KeyboardInterrupt:
                    row.update(status='CANCELLED')
                    raise
                except Exception as exc:
                    row.update(status='ERROR', exception_type=type(exc).__name__)
                finally:
                    row['duration_seconds'] = round(time.monotonic() - started, 3)
                    classify_contained_result(row, observed)
                    row['checks'] = []
                    for check in case['expected']:
                        actual = lookup(observed, check['path']) if isinstance(observed, dict) else MISSING
                        row['checks'].append({**check, 'expected': check['value'],
                                              'actual': '<MISSING>' if actual is MISSING else actual,
                                              'status': 'NOT_EVALUATED' if row['status'] in ('BLOCKED', 'ERROR', 'CANCELLED') else 'PASS' if matches(actual, check['op'], check['value']) else 'FAIL'})
                    artifact = f"outputs/{case['id']}-{mode}-{iteration}.json"
                    payload = {'run_id': run_id, 'case_id': case['id'], 'scope': row['scope'],
                               'status': row['status'], 'assertion_status': row.get('assertion_status', row['status']),
                               'outcome_assessment': row.get('outcome_assessment'), 'original_observed_output': observed,
                               'reason': row.get('reason'), 'exception_type': row.get('exception_type')}
                    (run_dir / artifact).write_text(json.dumps(redact(payload, secret), indent=2, ensure_ascii=False) + '\n')
                    row['output_file'] = artifact
                    save()
    except KeyboardInterrupt:
        state = 'cancelled'
        print('Run cancelled; completed results saved.')
    finally:
        save()
        if module is not None and callable(getattr(module, 'close', None)):
            module.close()
    if state != 'cancelled':
        state = 'completed'
    counts = save()
    print(json.dumps(counts))
    print('Report: ' + str(run_dir / 'report.html'))
    return 0 if rows and all(r['status'] == 'PASS' for r in rows) else 1


if __name__ == '__main__':
    sys.exit(main())
