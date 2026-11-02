"""Dibsly hooks for the published SafeRevoke CLI. No engine/classification logic here."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess

from saferevoke.external import ExternalAnalysis
from saferevoke.model import Grant, Lab, Workflow


def _local(name):
    path = Path(__file__).with_name(name + '.py')
    spec = importlib.util.spec_from_file_location('_dibsly_' + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def control(action, subject, permission, root, options):
    admin = _local('manage_permissions').DibslyAdmin('http://127.0.0.1:8093')
    if action != 'permissions':
        if action not in {'revoke', 'restore'}:
            raise ValueError('Unsupported Dibsly permission control')
        admin.change(subject, permission, action == 'revoke')
    _, permissions, revoked = admin.account(subject)
    return {'application': 'Dibsly', 'target': 'http://127.0.0.1:8093', 'subject': subject,
            'permissions': {name: 'REVOKED' if name in revoked else 'ACTIVE' for name in permissions}}


def create_analysis(root, output, options):
    hooks = _local('run_demo')
    java = Path(options.get('java', '')).resolve()
    javac = java.with_name('javac.exe' if os.name == 'nt' else 'javac')
    jar = root / 'target/dibsly-1.0.0.jar'
    if not java.is_file() or not javac.is_file() or not jar.is_file():
        raise ValueError('Set options.java to a Java 21 JDK executable and build Dibsly first')
    classes = output / 'connector-classes'
    classes.mkdir()
    source = Path(__file__).with_name('DibslyWorkflow.java')
    subprocess.run([str(javac), '--release', '21', '-cp', str(jar), '-d', str(classes), str(source)], check=True, timeout=60)
    command = [str(java), '-Xms32m', '-Xmx256m', '-cp', os.pathsep.join((str(classes), str(jar))), 'DibslyWorkflow']
    result = subprocess.run([*command, '--describe'], capture_output=True, text=True, encoding='utf-8', check=True, timeout=20)
    inventory = json.loads(result.stdout)
    grants = {item['id']: Grant(**item) for item in inventory['grants']}
    workflows = {name: Workflow(name, hooks.NAMES[name], 'Real authenticated HTTP form and database-effect assertions',
                  lambda ctx: None, 'HTTP 303', hooks.expected_effects(name)) for name in inventory['workflows']}
    lab = Lab(grants, {}, workflows, set(), {(g.resource, g.action) for g in grants.values()},
              {'create': 2, 'submit': 2, 'hire': 4, 'withdraw': 2, 'manage': 3}, {})
    adapter = hooks.DibslyAdapter(lab, command, output / 'temporary-runs')
    previous = os.environ.get('DIBSLY_CONNECTOR_TEST')
    os.environ['DIBSLY_CONNECTOR_TEST'] = 'true'

    def close():
        if previous is None:
            os.environ.pop('DIBSLY_CONNECTOR_TEST', None)
        else:
            os.environ['DIBSLY_CONNECTOR_TEST'] = previous
        if adapter.cleanups != len(adapter.completed) or any(adapter.runtime.iterdir()):
            raise RuntimeError('Connector cleanup verification failed; report is incomplete')

    def evidence():
        return {'application_jar_sha256': hashlib.sha256(jar.read_bytes()).hexdigest(),
                'completed_trials': len(adapter.completed), 'verified_cleanups': adapter.cleanups,
                'connector_trials': adapter.completed,
                'isolation': 'Disposable instances of the Dibsly JAR; fresh in-memory DB per trial, not the live presentation database',
                'scope': 'Four configured workflows and five grants; unexercised management remains UNKNOWN'}

    return ExternalAnalysis(lab, adapter, evidence, close)
