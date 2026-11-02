"""Check real connector output, independently of the engine's classification implementation."""
import json
from pathlib import Path
import sys


def verify(path):
    report = json.loads(Path(path).read_text(encoding='utf-8'))
    pairs = {'client_post': 'publish_project', 'talent_pitch': 'submit_pitch',
             'client_hire': 'hire_freelancer', 'talent_withdraw': 'withdraw_pitch'}
    assert report['summary'] == {'REQUIRED_ACCESS': 4, 'UNKNOWN': 1}, report['summary']
    assert report['coverage']['baseline_unexercised_grants'] == ['client_manage']
    assert len(report['baseline']) == 4 and all(run['success'] for run in report['baseline'].values())
    assert report['integration']['completed_trials'] == report['integration']['verified_cleanups'] == 24
    assert report['integration']['python_package_version'] == '0.1.0a3'
    assert 'site-packages' in report['integration']['python_package_path']
    assert not any((Path(path).parent / 'temporary-runs').iterdir())
    seen = set()
    for trial in report['connector_trials']:
        run = trial['run']; removed = trial['removed']
        key = (tuple(removed), run['workflow_id'])
        assert key not in seen
        seen.add(key)
        affected = bool(removed and pairs.get(removed[0]) == run['workflow_id'])
        assert run['success'] is not affected
        assert run['output'] == ('HTTP 403' if affected else 'HTTP 303')
        effects = run['side_effects']
        assert effects['same_login_session'] is True and effects['database_restored'] is True
        if affected:
            assert all(value == 0 for name, value in effects.items() if name not in ('same_login_session', 'database_restored'))
        else:
            assert effects == report['baseline'][run['workflow_id']]['side_effects']
        assert len(run['events']) == 1
        event = run['events'][0]
        assert event['allowed'] is not affected
        assert event['grant_ids'] == ([] if affected else report['baseline'][run['workflow_id']]['events'][0]['grant_ids'])
        assert not set(event['grant_ids']).intersection(removed)
    assert len(seen) == 24
    print('Verified 24 actual HTTP trials: four dependencies, one unknown grant, no writes on denied requests, stable sessions, and complete cleanup.')


if __name__ == '__main__':
    verify(sys.argv[1])
