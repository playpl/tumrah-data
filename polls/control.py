"""The polls control page on http://127.0.0.1:8765. Start, Stop and live progress for polls/engine.py.

The job runs as its own process, so closing this page or this server does not stop it; only Stop does.
Run with Python 3.13: python polls/control.py   (or Polls.bat)
"""
import json
import subprocess
import sys
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import engine

PORT = 8765
HOME = Path(__file__).resolve().parent
LOG = HOME / "engine.log"
LAUNCH = [sys.executable, str(HOME / "engine.py")]
DETACHED = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP


def log_tail():
    return LOG.read_text(encoding="utf-8", errors="replace").splitlines()[-3:] if LOG.exists() else []


def start(c, interval):
    if engine.status(c)["running"]:
        return False
    engine.put(c, "interval", interval)
    engine.STOP.unlink(missing_ok=True)
    engine.put(c, "beat", time.time())  # the page shows Running from the first poll
    with open(LOG, "w", encoding="utf-8") as out:
        subprocess.Popen(LAUNCH, cwd=HOME.parent, stdout=out, stderr=subprocess.STDOUT, creationflags=DETACHED)
    return True


class Page(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def reply(self, body, kind="application/json", code=200):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/":
            self.reply((HOME / "page.html").read_bytes(), "text/html; charset=utf-8")
        elif self.path == "/status":
            c = engine.db()
            body = engine.status(c) | {"stopping": engine.STOP.exists(), "log": log_tail()}
            c.close()
            self.reply(body)
        else:
            self.reply({"error": "not found"}, code=404)

    def do_POST(self):
        origin = self.headers.get("Origin")
        if origin and origin != f"http://127.0.0.1:{self.server.server_port}":
            return self.reply({"error": "other site"}, code=403)  # a web page must not start voting
        size = int(self.headers.get("Content-Length") or 0)
        data = json.loads(self.rfile.read(size) or "{}")
        interval = min(max(float(data.get("interval", 8)), 3), 60)
        c = engine.db()
        try:
            if self.path == "/start":
                return self.reply({"started": start(c, interval)})
            if self.path == "/stop":
                engine.STOP.touch()
                return self.reply({"stopping": True})
            if self.path == "/interval":
                engine.put(c, "interval", interval)
                return self.reply({"interval": interval})
            return self.reply({"error": "not found"}, code=404)
        finally:
            c.close()


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Page)
    webbrowser.open(f"http://127.0.0.1:{PORT}")
    print(f"Polls page: http://127.0.0.1:{PORT}  (closing this window does not stop the job)", flush=True)
    server.serve_forever()
