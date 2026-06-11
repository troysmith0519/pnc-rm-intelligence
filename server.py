#!/usr/bin/env python3
"""
PNC RM Intelligence — Local Proxy Server
Serves the HTML app AND proxies Alation API calls to avoid CORS.
Usage: python3 server.py
"""
import http.server, urllib.request, urllib.error, os, sys, json

ALATION_BASE = 'https://north-central-ds.mtse.alationcloud.com'
PORT = 8080

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
        for h in ('Authorization', 'Content-Type', 'Accept'):
            if v := self.headers.get(h):
                fwd[h] = v

        try:
            req = urllib.request.Request(target, data=body, method=method, headers=fwd)
            with urllib.request.urlopen(req, timeout=120) as resp:
                self.send_response(resp.status)
                self._cors()
                ct = resp.headers.get('Content-Type', 'application/json')
                self.send_header('Content-Type', ct)
                self.end_headers()
                while chunk := resp.read(4096):
                    self.wfile.write(chunk)
                    self.wfile.flush()
        except urllib.error.HTTPError as e:
            self.send_response(e.code)
            self._cors()
            self.end_headers()
            self.wfile.write(e.read())
        except Exception as e:
            self.send_response(502)
            self._cors()
            self.end_headers()
            self.wfile.write(json.dumps({'error': str(e)}).encode())

    def _cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Authorization, Content-Type, Accept')

    def log_message(self, fmt, *args):
        path = args[0] if args else ''
        if '/proxy/' in str(path):
            print(f'  → {fmt % args}')
        elif not str(path).endswith(('.css', '.js', '.ico')):
            print(f'  {fmt % args}')


if __name__ == '__main__':
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    server = http.server.HTTPServer(('', PORT), RMIntelligenceHandler)
    print(f'\n✓ PNC RM Intelligence running at:')
    print(f'  http://localhost:{PORT}/PNC-RM-Intelligence.html')
    print(f'\n✓ Proxying Alation API calls → {ALATION_BASE}')
    print(f'\n  Press Ctrl+C to stop\n')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nServer stopped.')
