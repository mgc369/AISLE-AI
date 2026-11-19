"""Dependency-free HTTP server. Launch: python run.py [--port 8000]."""
from __future__ import annotations

import argparse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from urllib.parse import urlsplit

from engine.algorithms import PlanningError, analyze_mission
from engine.scenarios import scenarios

ROOT = Path(__file__).resolve().parent
WEB = ROOT / 'web'


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB), **kwargs)

    def do_GET(self):
        if urlsplit(self.path).path == '/api/presets':
            self.write_json({'presets': scenarios()})
            return
        return super().do_GET()

    def do_POST(self):
        if urlsplit(self.path).path != '/api/analyze':
            self.write_json({'error': 'Unknown endpoint.'}, 404)
            return
        if self.headers.get('Content-Type', '').split(';')[0].strip().lower() != 'application/json':
            self.write_json({'error': 'Expected application/json.'}, 415)
            return
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if size < 1 or size > 200000:
                self.write_json({'error': 'Request is empty or too large.'}, 413)
                return
            payload = json.loads(self.rfile.read(size).decode('utf-8'))
            result = analyze_mission(payload)
            self.write_json(result)
        except (PlanningError, ValueError, TypeError, json.JSONDecodeError) as exc:
            self.write_json({'error': str(exc)}, 400)
        except Exception:
            self.log_error('Unexpected error during mission planning')
            self.write_json({'error': 'Unexpected server error.'}, 500)

    def write_json(self, data, status=200):
        body = json.dumps(data, separators=(',', ':'), allow_nan=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        print('[AISLE] ' + fmt % args)


def main():
    parser = argparse.ArgumentParser(description='AISLE AI — interactive warehouse intelligence lab')
    parser.add_argument('--port', type=int, default=8000)
    args = parser.parse_args()
    if not 0 <= args.port <= 65535:
        parser.error('--port must be between 0 and 65535.')
    try:
        server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    except OSError as exc:
        parser.exit(1, f'Cannot start AISLE AI on port {args.port}. {exc}\n')
    with server:
        print(f'AISLE AI running at http://localhost:{server.server_port}', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    main()
