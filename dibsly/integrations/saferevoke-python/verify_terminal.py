"""Verify terminal revoke/restore against the dedicated, synthetic presentation site."""
import http.cookiejar
import json
from pathlib import Path
import re
import subprocess
import sys
import urllib.request
from manage_permissions import DibslyAdmin, NoRedirect

ROOT = Path(__file__).resolve().parents[2]

def session(username):
    browser = DibslyAdmin.__new__(DibslyAdmin)
    browser.url = 'http://127.0.0.1:8093'
    browser.csrf = ''
    cookies = http.cookiejar.CookieJar()
    browser.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPCookieProcessor(cookies), NoRedirect())
    assert browser.request('/login')[0] == 200
    assert browser.request('/login', {'username': username, 'password': 'DibslyDemo2026!'})[0] == 302
    return browser, cookies

def command(action):
    subprocess.run([sys.executable, str(Path(__file__).with_name('manage_permissions.py')), action,
                    'freelancer.demo', 'SUBMIT_PROPOSAL'], check=True)

def main():
    client, _ = session('client.demo')
    talent, cookies = session('freelancer.demo')
    assert client.request('/app/new')[0] == 200
    assert client.request('/app/action/request', {'title': 'Verification: terminal permission control',
        'description': 'Synthetic verification project for testing account restrictions and session continuity.',
        'category': 'Development & IT', 'urgency': 'This week', 'budget': '25000'})[0] == 303
    status, content = client.request('/api/requests')
    assert status == 200
    project = max(item['id'] for item in json.loads(content))
    page = '/project?id=' + str(project)
    assert talent.request(page)[0] == 200
    before = [(c.name, c.value) for c in cookies]
    form = {'requestId': str(project), 'diagnosis': 'Deliver a tested site with documented handover.',
            'price': '20000', 'etaDays': '10', 'warrantyDays': '14'}
    _, _, old_revoked = DibslyAdmin('http://127.0.0.1:8093').account('freelancer.demo')
    try:
        command('revoke')
        denied, message = talent.request('/app/action/proposal', form)
        assert denied == 403 and 'SUBMIT_PROPOSAL (REVOKED)' in message
        assert 'name="proposalId"' not in client.request(page)[1]
        command('grant')
        restored, _ = talent.request('/app/action/proposal', form)
        assert restored == 303
        assert before == [(c.name, c.value) for c in cookies]
        page_text = talent.request(page)[1]
        pitch = re.search(r'name="proposalId" value="(\d+)"', page_text).group(1)
        assert talent.request('/app/action/withdraw', {'requestId': str(project), 'proposalId': pitch})[0] == 303
        result = {'terminalRevokeStatus': denied, 'terminalRestoreStatus': restored,
                  'sameLoginSession': True, 'deniedRequestCreatedNoPitch': True,
                  'testPitchWithdrawn': True, 'target': 'http://127.0.0.1:8093'}
        (ROOT/'verification/terminal-permissions.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        print(json.dumps(result, indent=2))
    finally:
        command('revoke' if 'SUBMIT_PROPOSAL' in old_revoked else 'grant')
        client.request('/app/action/cancel', {'requestId': str(project)})

if __name__ == '__main__':
    main()
