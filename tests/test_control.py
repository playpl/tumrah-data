import json
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "polls"))
import control  # noqa: E402
import engine  # noqa: E402


class Control(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        base = Path(self.dir.name)
        self.saved = engine.DB, engine.STOP, control.LOG, control.LAUNCH
        engine.DB, engine.STOP, control.LOG = base / "t.db", base / "stop.flag", base / "e.log"
        self.mark = base / "started"
        control.LAUNCH = [sys.executable, "-c", f"open(r'{self.mark}', 'a').write('x')"]
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), control.Page)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        engine.DB, engine.STOP, control.LOG, control.LAUNCH = self.saved
        time.sleep(0.2)
        self.dir.cleanup()

    def post(self, path, body=None, origin=None):
        headers = {"Content-Type": "application/json"} | ({"Origin": origin} if origin else {})
        req = urllib.request.Request(self.url + path, json.dumps(body or {}).encode(), headers)
        with urllib.request.urlopen(req) as r:
            return json.load(r)

    def status(self):
        with urllib.request.urlopen(self.url + "/status") as r:
            return json.load(r)

    def test_page_serves(self):
        with urllib.request.urlopen(self.url + "/") as r:
            self.assertIn(b"<title>Polls</title>", r.read())

    def test_start_launches_once_and_clears_an_old_stop(self):
        engine.STOP.touch()
        self.assertTrue(self.post("/start", {"interval": 12})["started"])
        self.assertFalse(engine.STOP.exists())
        self.assertFalse(self.post("/start")["started"])  # running: no second job
        status = self.status()
        self.assertTrue(status["running"])
        self.assertEqual(status["interval"], 12)
        time.sleep(1)
        self.assertEqual(self.mark.read_text(), "x")

    def test_stop_writes_the_flag(self):
        self.post("/stop")
        self.assertTrue(engine.STOP.exists())
        self.assertTrue(self.status()["stopping"])

    def test_interval_stays_inside_safe_limits(self):
        self.assertEqual(self.post("/interval", {"interval": 1})["interval"], 3)

    def test_another_website_cannot_start_voting(self):
        with self.assertRaises(urllib.error.HTTPError) as e:
            self.post("/start", origin="https://evil.example")
        self.assertEqual(e.exception.code, 403)
        time.sleep(0.3)
        self.assertFalse(self.mark.exists())


if __name__ == "__main__":
    unittest.main()
