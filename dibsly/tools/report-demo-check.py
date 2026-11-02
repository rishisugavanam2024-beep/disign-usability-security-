"""Exercise real HTTP report permissions and correlate a new denial with the library audit.
Creates one synthetic freelancer and restores its permission in finally; no projects are changed.
"""
import csv
import http.cookiejar
import io
import json
from pathlib import Path
import re
import urllib.error
import urllib.parse
import urllib.request
import uuid

BASE = 'http://127.0.0.1:8092'
REPORT = '/app/access/denied-report.csv'
checks = []
def check(label, condition):
    checks.append({'check': label, 'passed': bool(condition)})
    if not condition:
        raise AssertionError(label)
    print('PASS: ' + label)

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

class Session:
    def __init__(self):
        self.cookies = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPCookieProcessor(self.cookies), NoRedirect())
        self.csrf = ''
    def request(self, path, data=None):
        payload = urllib.parse.urlencode({'csrf': self.csrf, **data}).encode() if data is not None else None
        try:
            response = self.opener.open(BASE + path, payload, timeout=30)
        except urllib.error.HTTPError as ex:
            response = ex
        text = response.read().decode('utf-8')
        token = re.search(r'name="csrf" value="([^"]+)"', text)
        if token:
            self.csrf = token.group(1)
        return response.code, text, response.headers
    def login(self, name, password):
        self.request('/login')
        check('login ' + name, self.request('/login', {'username': name, 'password': password})[0] == 302)

admin, freelancer, guest = Session(), Session(), Session()
status, _, headers = guest.request(REPORT)
check('anonymous report request redirects to login', status in (302, 303) and headers['Location'].endswith('/login'))
admin.login('admin', 'DibslyAdmin2026!')
name = 'report.demo.' + uuid.uuid4().hex[:8]
freelancer.request('/register')
check('synthetic freelancer created', freelancer.request('/register', {'username': name, 'displayName': 'Report verification', 'password': 'TestingDibsly2026!', 'role': 'PROVIDER'})[0] == 302)
check('freelancer cannot download admin report', freelancer.request(REPORT)[0] == 403)
status, page, _ = admin.request('/app/access')
check('report link available in Access lab', status == 200 and REPORT in page)
row = next(row for row in re.findall(r'<article class="access-row">(.*?)</article>', page, re.S) if name in row)
user_id = re.search(r'name="userId" value="(\d+)"', row).group(1)
subject = 'dibsly:user:' + user_id
check('audit subject shown beside account', subject in row)
before = list(csv.DictReader(io.StringIO(admin.request(REPORT)[1])))
old_ids = {event['event_id'] for event in before}
check('baseline private read allowed', freelancer.request('/api/requests')[0] == 200)
cookies_before = [(cookie.name, cookie.value) for cookie in freelancer.cookies]
try:
    check('permission revoked', admin.request('/app/action/permission', {'userId': user_id, 'permission': 'VIEW_OPEN_REQUESTS', 'change': 'revoke'})[0] == 303)
    check('same-session private read denied', freelancer.request('/api/requests')[0] == 403)
    status, report, headers = admin.request(REPORT)
    events = list(csv.DictReader(io.StringIO(report)))
    check('CSV download headers', status == 200 and 'text/csv' in headers['Content-Type'] and 'attachment;' in headers['Content-Disposition'] and headers['Cache-Control'] == 'no-store')
    check('CSV complete row count', int(headers['X-Safe-Revoke-Denial-Count']) == len(events))
    check('only library denials exported', all(event['outcome'] == 'ACCESS_DENIED' for event in events))
    added = [event for event in events if event['event_id'] not in old_ids]
    check('exactly one new correlated denial', len(added) == 1 and added[0]['subject_id'] == subject and added[0]['permission'] == 'VIEW_OPEN_REQUESTS' and added[0]['reason'] == 'REVOKED' and added[0]['revision'] == '1')
    check('CSV includes UTC and version', added[0]['occurred_at_utc'].endswith('Z') and added[0]['library_version'] == '1.0.0')
    page = admin.request('/app/access')[1]
    check('denial also appears in audit table', subject in page and 'REVOKED' in page and 'revision 1' in page)
    output = Path('.local/reports')
    output.mkdir(parents=True, exist_ok=True)
    (output / 'denied-actions-verified.csv').write_bytes(report.encode('utf-8'))
finally:
    check('permission restored after check', admin.request('/app/action/permission', {'userId': user_id, 'permission': 'VIEW_OPEN_REQUESTS', 'change': 'restore'})[0] == 303)
check('same-session private read allowed again', freelancer.request('/api/requests')[0] == 200)
check('login cookie unchanged', cookies_before == [(cookie.name, cookie.value) for cookie in freelancer.cookies])
after = list(csv.DictReader(io.StringIO(admin.request(REPORT)[1])))
check('restoring retains denial history', any(event['event_id'] == added[0]['event_id'] for event in after))
Path('verification/report-demo.json').write_text(json.dumps({'checks': checks, 'denial': added[0], 'exportedRows': len(after)}, indent=2), encoding='utf-8')
print('All ' + str(len(checks)) + ' report checks passed.')
