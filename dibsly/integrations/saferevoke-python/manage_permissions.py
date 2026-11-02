"""Application-specific terminal controls using Dibsly's ordinary administrator forms.
This stdlib-only connector is separate from SafeRevoke's analysis engine.
"""
import argparse
import html
import http.cookiejar
import os
import re
import urllib.error
import urllib.parse
import urllib.request


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class DibslyAdmin:
    def __init__(self, url):
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != 'http' or parsed.hostname != '127.0.0.1' or parsed.port != 8093 or parsed.path not in ('', '/') or parsed.query or parsed.fragment or parsed.username:
            raise ValueError('Controls are restricted to the dedicated presentation at http://127.0.0.1:8093')
        self.url = url.rstrip('/')
        self.csrf = ''
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()), NoRedirect())
        status, _ = self.request('/login')
        if status != 200:
            raise RuntimeError('Start the presentation site first')
        status, _ = self.request('/login', {'username': 'admin', 'password': os.environ.get('DIBSLY_PRESENTATION_ADMIN_PASSWORD', 'DibslyAdmin2026!')})
        if status != 302:
            raise RuntimeError('Presentation administrator login failed')

    def request(self, path, data=None):
        body = urllib.parse.urlencode({'csrf': self.csrf, **data}).encode() if data is not None else None
        try:
            response = self.opener.open(self.url + path, body, timeout=20)
        except urllib.error.HTTPError as error:
            response = error
        text = response.read().decode('utf-8')
        token = re.search(r'name="csrf" value="([^"]+)"', text)
        if token:
            self.csrf = token.group(1)
        return response.code, text

    def account(self, username):
        status, page = self.request('/app/access')
        if status != 200:
            raise RuntimeError('Administrator account access is unavailable')
        for row in re.findall(r'<article class="access-row">(.*?)</article>', page, re.S):
            if re.search(r'<span class="quiet">' + re.escape(html.escape(username)) + r'\s*·', row):
                user_id = re.search(r'name="userId" value="(\d+)"', row).group(1)
                options = re.findall(r'<option>([A-Z_]+)</option>', row)
                revoked = re.search(r'<strong>Revoked:</strong>\s*\[([^]]*)\]', row)
                return user_id, options, set(revoked.group(1).split(', ')) if revoked and revoked.group(1) else set()
        raise ValueError('Account was not found in the presentation account list')

    def change(self, username, permission, revoke):
        user_id, permissions, _ = self.account(username)
        if permission not in permissions:
            raise ValueError('That permission is not part of this account role; restoration cannot grant a new role permission')
        status, _ = self.request('/app/action/permission', {'userId': user_id, 'permission': permission, 'change': 'revoke' if revoke else 'restore'})
        if status != 303:
            raise RuntimeError(f'Dibsly rejected the change (HTTP {status})')
        _, _, revoked = self.account(username)
        if (permission in revoked) != revoke:
            raise RuntimeError('Permission verification did not match the requested change')
        print(f'{username}: {permission} = {"REVOKED" if revoke else "ACTIVE"}')
        print('The next protected action in the existing browser session uses this permission state.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('permissions', 'revoke', 'grant', 'restore'))
    parser.add_argument('username')
    parser.add_argument('permission', nargs='?')
    args = parser.parse_args()
    admin = DibslyAdmin('http://127.0.0.1:8093')
    if args.action == 'permissions':
        _, permissions, revoked = admin.account(args.username)
        print('Dibsly application permissions for ' + args.username)
        for permission in permissions:
            print(f'  {permission}: {"REVOKED" if permission in revoked else "ACTIVE"}')
    else:
        if not args.permission:
            parser.error('A permission name is required')
        admin.change(args.username, args.permission, args.action == 'revoke')


if __name__ == '__main__':
    main()
