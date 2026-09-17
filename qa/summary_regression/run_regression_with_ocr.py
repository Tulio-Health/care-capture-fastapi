"""Run local safety/mock regression and opt-in live clinical OCR samples; no DB."""
import argparse
import os
import json
import html
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]

def write_suite_report(codes, include_live):
    results = ROOT / 'qa/results'
    mock = json.loads((results / 'report.json').read_text())
    live_path = results / 'clinical_ocr_all_live/report.json'
    live = json.loads(live_path.read_text()) if include_live and live_path.exists() else None
    report = {'generated_at': datetime.now(timezone.utc).isoformat(), 'command_exit_codes': codes,
              'mock_counts': mock.get('counts'), 'mock_run_id': mock.get('run_id'),
              'live_counts': {status:sum(row['status']==status for row in live['documents']) for status in sorted({row['status'] for row in live['documents']})} if live else None,
              'live_assessment': live.get('assessment') if live else None,
              'live_usage': {k:live.get('usage',{}).get(k) for k in ('calls','total_tokens')} if live else None,
              'database_writes':0}
    report['health'] = 'REQUIRES_ATTENTION' if any(codes) or (live and any(row['status'] != 'REVIEW_REQUIRED' for row in live['documents'])) else 'CLINICAL_REVIEW_PENDING'
    (results/'regression.json').write_text(json.dumps(report,indent=2)+'\n')
    page = '<!doctype html><meta charset="utf-8"><title>Summary regression</title><style>body{font:16px/1.5 system-ui;max-width:1000px;margin:40px auto}pre{white-space:pre-wrap}</style><h1>Summary regression</h1><p>Current local run. Model acceptance is not clinical approval; rejected documents do not establish usable extraction.</p><pre>'+html.escape(json.dumps(report,indent=2))+'</pre><p><a href="report.html">Full mock case results</a></p>'
    if live:
        page += '<p><a href="clinical_ocr_all_live/report.html">All nine live OCR documents, source links, transcriptions, summary candidates and rejection findings</a></p>'
    (results/'regression.html').write_text(page)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live-ocr', action='store_true', help='Also call OpenAI for all nine clinical OCR samples using qa/.env.regression.local.')
    parser.add_argument('--ocr-repeat', type=int, choices=range(1, 4), default=1, help='Live attempts per clinical sample, sharing one configured budget.')
    args = parser.parse_args()
    commands = [
        [sys.executable, '-m', 'unittest', 'discover', '-s', 'qa/summary_regression', '-p', 'test_*.py'],
        [sys.executable, 'qa/summary_regression/run_pack.py', '--mode', 'mock', '--execute'],
    ]
    if args.live_ocr:
        commands.append([sys.executable, 'qa/summary_regression/run_clinical_ocr.py', '--summarize', '--all-samples', '--repeat', str(args.ocr_repeat)])
    environment = dict(os.environ)
    environment["PATH"] = str(Path(sys.executable).parent) + os.pathsep + environment.get("PATH", "")
    codes = []
    for command in commands:
        codes.append(subprocess.run(command, cwd=ROOT, env=environment).returncode)
    write_suite_report(codes, args.live_ocr)
    print('Inspect qa/results/report.html and qa/results/clinical_ocr_all_live/report.html; live rejection/review is not a pass.')
    return int(any(codes))

if __name__ == '__main__':
    raise SystemExit(main())
