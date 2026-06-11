#!/usr/bin/env python3
"""
PNC RM Intelligence — Local Proxy Server with OAuth
Usage: python3 server.py
"""
import http.server, urllib.request, urllib.error, urllib.parse, ssl, os, json

ALATION_BASE  = 'https://north-central-ds.mtse.alationcloud.com'
CLIENT_ID     = 'adbab6e3-e395-45b8-870a-f6ea9591540f'
CLIENT_SECRET = 'MDBiN2YzNDEtNDAyMi00MWM2LTgzZjQtMmIyZWZjNzRhZjcz'
REDIRECT_URI  = 'http://localhost:8080/oauth/callback'
PORT          = 8080

SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE


class RMIntelligenceHandler(http.server.SimpleHTTPRequestHandler):
    oauth_token = None  # shared across all requests

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_GET(self):
        if self.path.startswith('/oauth/start'):
            self._oauth_start()
        elif self.path.startswith('/oauth/callback'):
            self._oauth_callback()
        elif self.path.startswith('/oauth/status'):
            self._oauth_status()
        elif self.path.startswith('/proxy/'):
            self._proxy('GET')
        else:
            super().do_GET()

    def do_POST(self):
        if self.path.startswith('/proxy/'):
            self._proxy('POST')
        else:
            super().do_POST()

    def _oauth_start(self):
        params = urllib.parse.urlencode({
            'client_id':     CLIENT_ID,
            'response_type': 'code',
            'redirect_uri':  REDIRECT_URI,
        })
        auth_url = f'{ALATION_BASE}/oauth/authorize/?{params}'
        print(f'  → OAuth redirect: {auth_url[:80]}')
        self.send_response(302)
        self.send_header('Location', auth_url)
        self._cors()
        self.end_headers()

    def _oauth_callback(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        code  = params.get('code',  [''])[0]
        error = params.get('error', [''])[0]

        if error or not code:
            print(f'  OAuth error: {error}')
            self._redirect_with_status('error', error or 'no code returned')
            return

        print(f'  OAuth code received, exchanging for token...')
        token_body = urllib.parse.urlencode({
            'grant_type':    'authorization_code',
            'code':          code,
            'redirect_uri':  REDIRECT_URI,
            'client_id':     CLIENT_ID,
            'client_secret': CLIENT_SECRET,
        }).encode()

        req = urllib.request.Request(
            f'{ALATION_BASE}/oauth/token/',
            data=token_body, method='POST',
            headers={'Content-Type': 'application/x-www-form-urlencoded'}
        )
        try:
            with urllib.request.urlopen(req, context=SSL_CTX, timeout=30) as r:
                data = json.loads(r.read())
                token = data.get('access_token', '')
                if token:
                    RMIntelligenceHandler.oauth_token = token
                    print(f'  ✓ OAuth token stored: ...{token[-8:]}')
                    self._redirect_with_status('success', '')
                else:
                    print(f'  OAuth response: {data}')
                    self._redirect_with_status('error', 'no access_token in response')
        except Exception as e:
            print(f'  OAuth token exchange failed: {e}')
            self._redirect_with_status('error', str(e))

    def _redirect_with_status(self, status, msg):
        dest = f'/PNC-RM-Intelligence.html#oauth_{status}'
        if msg:
            dest += '=' + urllib.parse.quote(msg)
        self.send_response(302)
        self.send_header('Location', dest)
        self._cors()
        self.end_headers()

    def _oauth_status(self):
        self.send_response(200)
        self._cors()
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        connected = bool(RMIntelligenceHandler.oauth_token)
        self.wfile.write(json.dumps({'connected': connected}).encode())

    def _proxy(self, method):
        target = ALATION_BASE + self.path[len('/proxy'):]
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length) if length else None

        fwd = {}
        for h in ('Content-Type', 'Accept'):
            v = self.headers.get(h)
            if v:
                fwd[h] = v

        # Use OAuth token if available, otherwise fall back to manual token
        token = RMIntelligenceHandler.oauth_token or \
                self.headers.get('X-Session-Id', '') or \
                self.headers.get('Authorization', '').replace('Bearer ', '')
        if token:
            fwd['Authorization'] = f'Bearer {token}'

        print(f'  PROXY {method} {target[:80]}')
        src = 'OAuth' if RMIntelligenceHandler.oauth_token else 'manual'
        if token:
            print(f'  Auth ({src}): ...{token[-8:]}')

        try:
            req = urllib.request.Request(target, data=body, method=method, headers=fwd)
            with urllib.request.urlopen(req, timeout=120, context=SSL_CTX) as resp:
                print(f'  → {resp.status} OK')
                self.send_response(resp.status)
                self._cors()
                ct = resp.headers.get('Content-Type', 'application/json')
                self.send_header('Content-Type', ct)
                self.end_headers()
                while True:
                    chunk = resp.read(4096)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    self.wfile.flush()
        except urllib.error.HTTPError as e:
            body_text = e.read()
            print(f'  → HTTP {e.code}: {body_text[:200]}')
            self.send_response(e.code)
            self._cors()
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(body_text)
        except Exception as e:
            print(f'  → ERROR: {type(e).__name__}: {e}')
            self.send_response(502)
            self._cors()
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'error': str(e)}).encode())

    def _cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Authorization, Content-Type, Accept, X-Session-Id')

    def log_message(self, fmt, *args):
        path = str(args[0]) if args else ''
        if '/proxy/' not in path and 'favicon' not in path:
            print(f'  {fmt % args}')


if __name__ == '__main__':
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    server = http.server.HTTPServer(('', PORT), RMIntelligenceHandler)
    print(f'\n✓ PNC RM Intelligence running at:')
    print(f'  http://localhost:{PORT}/PNC-RM-Intelligence.html')
    print(f'\n✓ OAuth: click "Connect via Alation" in the app')
    print(f'  Callback: {REDIRECT_URI}')
    print(f'\n  Press Ctrl+C to stop\n')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nServer stopped.')
