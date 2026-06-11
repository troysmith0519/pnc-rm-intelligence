#!/usr/bin/env python3
"""
PNC RM Intelligence — Local Proxy Server
Serves the HTML app AND proxies Alation API calls to avoid CORS.
Usage: python3 server.py
"""
import http.server, urllib.request, urllib.error, ssl, os, sys, json

ALATION_BASE = 'https://north-central-ds.mtse.alationcloud.com'
PORT = 8080

# SSL context — bypass cert verification for MTSE demo instance
SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE

class RMIntelligenceHandler(http.server.SimpleHTTPRequestHandler):

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_GET(self):
        if self.path.startswith('/proxy/'):
            self._proxy('GET')
        else:
            super().do_GET()

    def do_POST(self):
        if self.path.startswith('/proxy/'):
            self._proxy('POST')
        else:
            super().do_POST()

    def _proxy(self, method):
        target = ALATION_BASE + self.path[len('/proxy'):]
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length) if length else None

        fwd = {}
        for h in ('Content-Type', 'Accept'):
            v = self.headers.get(h)
            if v:
                fwd[h] = v

        # Auth: try Bearer first, fall back to session cookie
        auth = self.headers.get('Authorization', '')
        session_id = self.headers.get('X-Session-Id', '')
        if auth:
            fwd['Authorization'] = auth
        if session_id:
            fwd['Cookie'] = f'sessionid={session_id}'

        print(f'  PROXY {method} {target[:80]}')
        if auth:
            print(f'  Auth: Bearer ...{auth[-8:]}')
        if session_id:
            print(f'  Session: ...{session_id[-8:]}')

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
            self.wfile.write(json.dumps({'error': str(e), 'type': type(e).__name__}).encode())

    def _cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Authorization, Content-Type, Accept')

    def log_message(self, fmt, *args):
        path = str(args[0]) if args else ''
        if '/proxy/' not in path and not path.endswith(('.ico',)):
            print(f'  {fmt % args}')


if __name__ == '__main__':
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    server = http.server.HTTPServer(('', PORT), RMIntelligenceHandler)
    print(f'\n✓ PNC RM Intelligence running at:')
    print(f'  http://localhost:{PORT}/PNC-RM-Intelligence.html')
    print(f'\n✓ Proxying → {ALATION_BASE}')
    print(f'  (SSL verification disabled for MTSE demo instance)')
    print(f'\n  Press Ctrl+C to stop\n')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nServer stopped.')
