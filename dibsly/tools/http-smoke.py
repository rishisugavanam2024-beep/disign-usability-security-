"""End-to-end checks against an explicitly enabled local demo. Creates clearly named test accounts/projects."""
import urllib.request, urllib.parse, urllib.error, http.cookiejar, re, json, time, uuid
from pathlib import Path
from datetime import date
import os

BASE = os.environ.get('DIBSLY_SMOKE_URL', 'http://127.0.0.1:8092')
assert BASE in ('http://127.0.0.1:8092', 'http://127.0.0.1:8093')
checks = []
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl): return None
class Session:
    def __init__(self):
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()), NoRedirect())
        self.csrf = ''
    def request(self, path, data=None):
        payload = urllib.parse.urlencode(data).encode() if data is not None else None
        try: response = self.opener.open(urllib.request.Request(BASE+path, payload), timeout=45)
        except urllib.error.HTTPError as exc: response = exc
        body = response.read().decode('utf-8', errors='replace'); token = re.search(r'name="csrf" value="([^"]+)"', body)
        if token: self.csrf = token.group(1)
        return response.code, body, response.headers
    def post(self, path, **data): return self.request(path, {'csrf':self.csrf, **data})
    def register(self, name, role):
        self.request('/register')
        result = self.post('/register', username=name, displayName='Test '+name, password='TestingDibsly2026!', role=role)
        check('register '+role, result[0] == 302)
    def login(self, username, password):
        self.request('/login'); result=self.post('/login',username=username,password=password)
        check('login '+username,result[0]==302)
def check(label, condition):
    checks.append({'check':label,'passed':bool(condition)})
    if not condition: raise AssertionError(label)
    print('PASS: '+label, flush=True)
def project(client, title='Smoke test: a thoughtful Java project'):
    client.request('/app/new')
    result=client.post('/app/action/request',title=title,description='Create a clear application with tests and documentation. <script>alert(1)</script>\tKeep examples readable.',category='Development & IT',urgency='This week',budget='25000')
    check('publish project',result[0]==303)
    return int(result[2]['Location'].split('=')[-1])
def pitch(user, pid, quote='20000'):
    return user.post('/app/action/proposal',requestId=pid,diagnosis='I will deliver working software with tests and a practical handover.',price=quote,etaDays='10',warrantyDays='14')

guest=Session()
for _ in range(30):
    try:
        status,body,_=guest.request('/health')
        if status==200: break
    except Exception: time.sleep(1)
check('health endpoint',status==200)
for path in ['/', '/explore', '/how-it-works', '/about', '/contact', '/privacy', '/register', '/login', '/assets/app.css', '/assets/app.js', '/assets/manrope.ttf']:
    result=guest.request(path); check('public route '+path,result[0]==200)
check('unauthenticated API rejected',guest.request('/api/requests')[0]==401)
check('custom 404', 'org.apache' not in guest.request('/does-not-exist')[1])
suffix=uuid.uuid4().hex[:7]
client, other, freelancer, second, admin = [Session() for _ in range(5)]
client.register('test.client.'+suffix,'CUSTOMER'); other.register('test.other.'+suffix,'CUSTOMER')
freelancer.register('test.talent.'+suffix,'PROVIDER'); second.register('test.second.'+suffix,'PROVIDER')
admin.login('admin','DibslyAdmin2026!')
pid=project(client)
result=guest.request('/project?id='+str(pid)); check('user text escaped','&lt;script&gt;' in result[1] and '<script>alert(1)' not in result[1])
result=client.request('/api/requests'); check('valid JSON with control characters',any(p['id']==pid for p in json.loads(result[1])))
check('API no-store',result[2].get('Cache-Control')=='no-store')
check('CSRF rejection',freelancer.post('/app/action/proposal',csrf='wrong',requestId=pid)[0]==403)
check('buyer cannot pitch',pitch(client,pid)[0]==403)
check('freelancer pitch succeeds',pitch(freelancer,pid)[0]==303)
check('duplicate pitch rejected',pitch(freelancer,pid)[0]==422)
check('second freelancer pitch succeeds',pitch(second,pid,'22000')[0]==303)
page=freelancer.request('/project?id='+str(pid))[1]
check('competing pitches hidden','Test test.second.'+suffix not in page)
page=client.request('/project?id='+str(pid))[1]
offers=re.findall(r'name="proposalId" value="(\d+)"',page)
check('client sees both pitches',len(offers)==2)
check('non-owner cannot hire',other.post('/app/action/accept',requestId=pid,proposalId=offers[0],date=date.today().isoformat())[0] in (403,422))
check('invalid date handled',client.post('/app/action/accept',requestId=pid,proposalId=offers[0],date='garbage')[0]==422)
check('hire accepted',client.post('/app/action/accept',requestId=pid,proposalId=offers[0],date=date.today().isoformat())[0]==303)
check('repeated hire rejected',client.post('/app/action/accept',requestId=pid,proposalId=offers[0],date=date.today().isoformat())[0]==422)
check('closed project rejects pitch',pitch(freelancer,pid)[0]==422)
check('private project denied to outsiders',other.request('/project?id='+str(pid))[0]==403)
check('complete contract',client.post('/app/action/complete',requestId=pid)[0]==303)
pid2=project(client,'Smoke test: permission revocation flow')
freelancer.request('/project?id='+str(pid2))
adminpage=admin.request('/app/access')[1]
check('native account access page', 'Manage account access.' in adminpage and 'Safe Revoke' not in adminpage)
account=re.search(r'<article class="access-row">(?:(?!</article>).)*test\.talent\.'+suffix+r'(?:(?!</article>).)*name="userId" value="(\d+)"',adminpage,re.S)
check('admin can inspect test account',account is not None)
target=account.group(1)
jar=next(h.cookiejar for h in freelancer.opener.handlers if isinstance(h,urllib.request.HTTPCookieProcessor))
session_before=[(c.name,c.value) for c in jar]
check('non-admin cannot revoke',freelancer.post('/app/action/permission',userId=target,permission='SUBMIT_PROPOSAL',change='revoke')[0]==403)
check('invalid permission change rejected',admin.post('/app/action/permission',userId=target,permission='SUBMIT_PROPOSAL',change='invalid')[0]==422)
check('revoke permission',admin.post('/app/action/permission',userId=target,permission='SUBMIT_PROPOSAL',change='revoke')[0]==303)
check('repeated revoke is safe',admin.post('/app/action/permission',userId=target,permission='SUBMIT_PROPOSAL',change='revoke')[0]==303)
denied=pitch(freelancer,pid2)
check('stale session rejected after revoke',denied[0]==403)
check('native permission denial displayed','SUBMIT_PROPOSAL (REVOKED)' in denied[1])
audit_page=admin.request('/app/access')[1]
check('audit records denial','DENIED' in audit_page)
check('native audit identifies permission','SUBMIT_PROPOSAL / REVOKED' in audit_page)
check('restore permission',admin.post('/app/action/permission',userId=target,permission='SUBMIT_PROPOSAL',change='restore')[0]==303)
check('same session succeeds after restore',pitch(freelancer,pid2)[0]==303)
check('session cookie unchanged across revoke and restore',session_before==[(c.name,c.value) for c in jar])
check('revoke read permission',admin.post('/app/action/permission',userId=target,permission='VIEW_OPEN_REQUESTS',change='revoke')[0]==303)
check('revoked read permission blocks API',freelancer.request('/api/requests')[0]==403)
check('restore read permission',admin.post('/app/action/permission',userId=target,permission='VIEW_OPEN_REQUESTS',change='restore')[0]==303)
check('restored read permission permits API',freelancer.request('/api/requests')[0]==200)
ownpage=freelancer.request('/project?id='+str(pid2))[1]
ownoffer=re.search(r'name="proposalId" value="(\d+)"',ownpage).group(1)
check('withdraw pitch',freelancer.post('/app/action/withdraw',requestId=pid2,proposalId=ownoffer)[0]==303)
check('cancel open project',client.post('/app/action/cancel',requestId=pid2)[0]==303)
check('admin access denied to freelancer',freelancer.request('/app/access')[0]==403)
result=client.post('/logout'); check('logout',result[0]==302)
check('session gone',client.request('/api/requests')[0]==401)
out=Path('verification');out.mkdir(exist_ok=True)
(out/'http-smoke.json').write_text(json.dumps(checks,indent=2))
print(f'{len(checks)} HTTP checks passed.')
