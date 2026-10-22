"""Recompute the paper from frozen vintage panels; preserve explicit source-audit scope."""
from pathlib import Path
import json
import os
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
STEPS = [
    'research.py', 'extensions.py', 'validate_research.py',
    'annual_phases.py', 'validate_annual_phases.py',
    'benchmark_feasibility.py', 'revision_benchmark.py',
    'validate_revision_benchmark.py', 'paper/build_sections.py',
    'paper/validate_denominator_sensitivity.py', 'paper/validate_evidence.py', 'paper/validate_submission_checks.py',
]

def main():
    check = subprocess.run([sys.executable, str(ROOT/'verify_archive.py')], cwd=ROOT)
    if check.returncode:
        raise SystemExit(check.returncode)
    logs = ROOT / 'run_logs'
    logs.mkdir(exist_ok=True)
    (ROOT / 'results').mkdir(exist_ok=True)
    env = dict(os.environ, PYTHONNOUSERSITE='1', PYTHONDONTWRITEBYTECODE='1',
               MPLCONFIGDIR=str(logs / 'matplotlib'), PYTHONUTF8='1',
               PYTHONIOENCODING='utf-8', TEMP=str(logs / 'tmp'), TMP=str(logs / 'tmp'))
    (logs / 'tmp').mkdir(exist_ok=True)
    records = []
    for step in STEPS + ['synthetic tests']:
        command = ([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests']
                   if step == 'synthetic tests' else [sys.executable, step])
        started = time.monotonic()
        print(step, flush=True)
        log = logs / (step.replace('/', '_').replace(' ', '_') + '.log')
        with log.open('w', encoding='utf-8') as stream:
            result = subprocess.run(command, cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT)
        records.append({'step': step, 'returncode': result.returncode,
                        'seconds': round(time.monotonic() - started, 2),
                        'log': str(log.relative_to(ROOT))})
        (logs / 'execution.json').write_text(json.dumps(records, indent=2), encoding='utf-8')
        if result.returncode:
            print(log.read_text(encoding='utf-8')[-6000:])
            raise SystemExit(result.returncode)
    print('All compact-package analyses and validations completed; original workbook extraction was not rerun.')

if __name__ == '__main__':
    main()
