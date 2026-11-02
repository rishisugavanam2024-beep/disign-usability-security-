"""Externally test the packaged Dibsly site with the original installed Python SafeRevoke engine."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import uuid

import saferevoke
from saferevoke.adapters.callback import StateHooks
from saferevoke.adapters.command import CommandAdapter
from saferevoke.engine import SafeRevokeEngine
from saferevoke.model import Grant, Lab, Workflow
from saferevoke.report import render_html, render_json

ROOT = Path(__file__).resolve().parents[2]
SOURCE = Path(__file__).with_name('DibslyWorkflow.java')
NAMES = {
    'publish_project': 'Client publishes a project',
    'submit_pitch': 'Freelancer submits a pitch',
    'hire_freelancer': 'Client hires a freelancer',
    'withdraw_pitch': 'Freelancer withdraws a pitch',
}
EFFECTS = {
    'publish_project': {'projects': 1},
    'submit_pitch': {'pitches': 1},
    'hire_freelancer': {'contracts': 1, 'booked_projects': 1, 'accepted_pitches': 1},
    'withdraw_pitch': {'withdrawn_pitches': 1},
}
COUNTS = ('projects', 'pitches', 'contracts', 'withdrawn_pitches', 'booked_projects', 'accepted_pitches')


def expected_effects(workflow):
    return {**{key: EFFECTS[workflow].get(key, 0) for key in COUNTS},
            'same_login_session': True, 'database_restored': True}


class DibslyAdapter(CommandAdapter):
    def __init__(self, lab, command, runtime):
        self.runtime = runtime.resolve()
        self.runtime.mkdir(parents=True, exist_ok=True)
        self.completed = []
        self.cleanups = 0
        super().__init__(lab, command, StateHooks(self._snapshot, lambda removed: None, self._restore),
                         test_environment=True, timeout=90)

    def _snapshot(self):
        # A separate JVM/in-memory DB, session, and owned working directory for every variant.
        directory = tempfile.TemporaryDirectory(prefix='trial-', dir=self.runtime)
        self.cwd = directory.name
        return directory

    def _restore(self, directory):
        owned = Path(directory.name).resolve()
        if owned.parent != self.runtime or not owned.name.startswith('trial-'):
            raise RuntimeError('Refusing to clean an unowned connector directory')
        directory.cleanup()
        if owned.exists():
            raise RuntimeError('Connector directory cleanup was incomplete')
        self.cleanups += 1

    def run(self, workflow):
        label = ', '.join(sorted(self.removed)) or 'baseline'
        print(f'  {workflow.id} [{label}]', flush=True)
        result = super().run(workflow)
        if result.side_effects.get('database_restored') is not True:
            raise RuntimeError('Dibsly did not verify database restoration')
        self.completed.append({'removed': sorted(self.removed), 'run': result.to_dict()})
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--java', default=shutil.which('java'))
    parser.add_argument('--jar', type=Path, default=ROOT / 'target/dibsly-1.0.0.jar')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--baseline-only', action='store_true', help='Run the four website workflows without removing grants')
    args = parser.parse_args()
    if not args.java or not args.jar.is_file():
        parser.error('Provide Java 21 and a built Dibsly application JAR')
    java = Path(args.java).resolve()
    javac = java.with_name('javac.exe' if os.name == 'nt' else 'javac')
    if not javac.is_file():
        parser.error('--java must point to a JDK 21 java executable, not a launcher shim')
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]
    output = (args.output or ROOT / 'reports/python-saferevoke' / run_id).resolve()
    # Refuse accidental overwriting of an earlier report or arbitrary existing directory.
    output.mkdir(parents=True, exist_ok=False)
    classes = output / 'connector-classes'
    classes.mkdir()
    subprocess.run([str(javac), '--release', '21', '-cp', str(args.jar.resolve()), '-d', str(classes), str(SOURCE)], check=True)
    command = [str(java), '-Xms32m', '-Xmx256m', '-cp', os.pathsep.join((str(classes), str(args.jar.resolve()))), 'DibslyWorkflow']
    description = subprocess.run([*command, '--describe'], capture_output=True, text=True, encoding='utf-8', check=True, timeout=20)
    inventory = json.loads(description.stdout)
    grants = {item['id']: Grant(**item) for item in inventory['grants']}
    workflows = {key: Workflow(key, NAMES[key], 'Real authenticated HTTP form and database-effect assertions',
                              lambda ctx: None, 'HTTP 303', expected_effects(key)) for key in inventory['workflows']}
    lab = Lab(grants, {}, workflows, set(), {(g.resource, g.action) for g in grants.values()},
              {'create': 2, 'submit': 2, 'hire': 4, 'withdraw': 2, 'manage': 3}, {})
    adapter = DibslyAdapter(lab, command, output / 'temporary-runs')
    version = importlib.metadata.version('saferevoke')
    print(f'Python SafeRevoke {version}: {saferevoke.__file__}', flush=True)
    print(f'Target: {args.jar.resolve()}', flush=True)
    print('Isolation: fresh in-memory database and real loopback Dibsly server per workflow.', flush=True)
    old_opt_in = os.environ.get('DIBSLY_CONNECTOR_TEST')
    os.environ['DIBSLY_CONNECTOR_TEST'] = 'true'
    try:
        if args.baseline_only:
            runs = {}
            for workflow in workflows.values():
                snapshot = adapter.snapshot()
                try:
                    adapter.deny(set())
                    run = adapter.run(workflow)
                    if not run.success or run.output != workflow.expected_output or run.side_effects != workflow.expected_side_effects:
                        raise RuntimeError(f'Baseline did not meet website assertions: {workflow.id}')
                    runs[workflow.id] = run.to_dict()
                finally:
                    adapter.restore(snapshot)
            report = {'baseline': runs, 'result': '4 baseline workflows passed; no permissions removed'}
        else:
            # All classifications below are produced by the original installed Python engine.
            report = SafeRevokeEngine(lab, adapter).analyze()
        if adapter.cleanups != len(adapter.completed) or any(adapter.runtime.iterdir()):
            raise RuntimeError('Trial cleanup verification failed')
        report['integration'] = {
            'application': 'Dibsly', 'connector': 'external CommandAdapter with real HTTP requests',
            'python_package_version': version, 'python_package_path': str(Path(saferevoke.__file__).resolve()),
            'application_jar_sha256': hashlib.sha256(args.jar.read_bytes()).hexdigest(),
            'connector_source_sha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
            'completed_trials': len(adapter.completed), 'verified_cleanups': adapter.cleanups,
            'generated_at_utc': datetime.now(timezone.utc).isoformat(),
            'authorization_boundary': 'Dibsly uses application-owned JDBC authorization with no SafeRevoke runtime dependency; the installed Python package externally analyzes removal effects.',
            'scope': 'Four marketplace writes, two synthetic users, five effective per-user grants. Private-read checks and other branches are not inventoried.',
            'isolation': 'Per-trial JVM and in-memory H2; full SQL snapshot restored and compared, server/session closed, temporary files removed.',
            'benchmark_note': 'Engine benchmark fields are generic model counters, not a production performance measurement.',
        }
        report['connector_trials'] = adapter.completed
        (output / 'report.json').write_text(render_json(report), encoding='utf-8')
        if not args.baseline_only:
            (output / 'report.html').write_text(render_html(report), encoding='utf-8')
            print('Findings: ' + json.dumps(report['summary']), flush=True)
            print('HTML report: ' + str(output / 'report.html'), flush=True)
        else:
            print(report['result'], flush=True)
        print('JSON evidence: ' + str(output / 'report.json'), flush=True)
        return report
    finally:
        if old_opt_in is None:
            os.environ.pop('DIBSLY_CONNECTOR_TEST', None)
        else:
            os.environ['DIBSLY_CONNECTOR_TEST'] = old_opt_in


if __name__ == '__main__':
    main()
