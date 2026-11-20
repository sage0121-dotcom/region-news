# -*- coding: utf-8 -*-
"""지역 동향 모니터 - PC에서 미리보기용 로컬 서버 (선택 사항)

실제 사용은 GitHub Pages 웹페이지로 합니다. 이 서버는 PC에서 확인하거나,
목록에 없는 기관을 실시간으로 검색할 때만 씁니다.

  python server.py   →  http://localhost:8765
"""
import json
import mimetypes
import os
import time
import urllib.parse
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

import collector

PORT = int(os.environ.get("PORT", "8765"))
BASE = Path(__file__).resolve().parent
mimetypes.add_type("application/manifest+json", ".webmanifest")
mimetypes.add_type("text/javascript", ".js")
_cache = {}


class H(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(BASE), **kw)

    def log_message(self, fmt, *a):
        print("[%s] %s" % (time.strftime("%H:%M:%S"), fmt % a), flush=True)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        if u.path == "/api/raw":   # 실시간 수집 (로컬 전용)
            name = urllib.parse.parse_qs(u.query).get("q", [""])[0].strip()[:40]
            if not name:
                return self._json(400, {"error": "q required"})
            hit = _cache.get(name)
            if not hit or time.time() - hit[0] > 600:
                hit = (time.time(), collector.collect(name))
                _cache[name] = hit
            return self._json(200, hit[1])
        if u.path.endswith((".py", ".yml")) or "/." in u.path:
            return self._json(404, {"error": "not found"})
        return super().do_GET()

    def _json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    import sys
    import webbrowser
    try:
        httpd = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    except OSError:
        print(f"이미 {PORT}번 포트에서 실행 중입니다. 브라우저만 엽니다.", flush=True)
        webbrowser.open(f"http://localhost:{PORT}")
        sys.exit(0)
    print(f"지역 동향 모니터 미리보기 →  http://localhost:{PORT}   (종료: Ctrl+C 또는 창 닫기)", flush=True)
    if "--no-browser" not in sys.argv:
        webbrowser.open(f"http://localhost:{PORT}")   # 서버가 준비된 뒤 브라우저 열기
    httpd.serve_forever()
