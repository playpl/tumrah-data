"""Gemini web, the only way in: the owner's four signed-in Chrome profiles. No cookie files, no keep-alive, no gweb
(owner, 2026-11-17: "Completely replace your old cookie stuff").

Reuses tumrah-book's driver, C:/Users/Ahmed/Desktop/tumrah-book/flow/images/browser.py:
- profiles ~/.tumrah-chrome/acct1..acct4, one Google account each; the owner signs in once, by hand, with
  `py -m flow.images.browser login <n>` (run from the tumrah-book folder). No code ever types a password.
- runs start the same profile with --remote-debugging-port=934<n> and drive it over CDP (Playwright); how Chrome shows
  is `~/.tumrah-chrome/show.txt` (headless | hidden | visible).
- the model is picked before every prompt; the send is retried until the prompt box empties; `acct<n>.busy` (holding
  the PID) keeps two runs off one account; never two Chromes on one profile folder.
- a profile on a sign-in page or a CAPTCHA is reported and skipped (another account takes the job).

    py gemini_browser.py status        which profiles are signed in (opens each; also cached in status.json)

`ask(prompt, model, attach, wait)` -> (text or None, meta): attachments (audio, PDF, text, pictures) are pasted into
the prompt box as files, the answer's body is read as text.
"""
import base64
import json
import sys
import time
from pathlib import Path

BOOK = Path(r"C:\Users\Ahmed\Desktop\tumrah-book")
HOME = Path.home() / ".tumrah-chrome"
ACCOUNTS = (1, 2, 3, 4)
# The owner's names -> the text of Gemini's mode menu option (the option holds the model's Latin name in every UI language).
MODELS = {"flash-lite": "Flash-Lite", "gemini-flash-lite": "Flash-Lite", "flash": "Flash", "gemini-flash": "Flash",
          "hydrogen": "Hydrogen"}
TYPES = {".ogg": "audio/ogg", ".opus": "audio/ogg", ".m4a": "audio/mp4", ".mp3": "audio/mpeg", ".wav": "audio/wav",
         ".pdf": "application/pdf", ".txt": "text/plain", ".md": "text/plain", ".jsonl": "text/plain",
         ".json": "application/json", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}

PASTE_FILE = """async ([b64, name, type]) => {
  const bin = atob(b64), arr = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
  const dt = new DataTransfer();
  dt.items.add(new File([arr], name, {type}));
  const ed = document.querySelector('div.ql-editor');
  ed.focus();
  ed.dispatchEvent(new ClipboardEvent('paste', {clipboardData: dt, bubbles: true, cancelable: true}));
}"""
# Only the answer's body: the response's own innerText starts with a screen-reader label ("قال Gemini" = "Gemini said").
LAST_TEXT = """() => { const r = [...document.querySelectorAll('model-response')].pop(); if (!r) return '';
  const b = r.querySelector('message-content .markdown, message-content, .markdown'); return (b || r).innerText; }"""


def driver():
    if str(BOOK) not in sys.path:
        sys.path.insert(0, str(BOOK))
    from flow.images import browser
    return browser


def model_name(model):
    return MODELS.get((model or "flash-lite").lower(), model)


def ask_on(pw, n, prompt, attach=(), wait=300, model="flash-lite"):
    """The answer's text to `prompt` with `attach` pasted as files, on account n. Raises a named fault."""
    b = driver()
    lock = b.take(n)
    pg = None
    try:
        pg = b._open(pw, n, model_name(model))
        before = pg.evaluate(b.ANSWERS)
        pg.locator("div.ql-editor").first.fill(prompt)
        for f in map(Path, attach):
            pg.evaluate(PASTE_FILE, [base64.b64encode(f.read_bytes()).decode(), f.name,
                                     TYPES.get(f.suffix.lower(), "application/octet-stream")])
        if attach:
            time.sleep(3)
        b._send(pg, n)                                  # tried again every 4 s while a file uploads
        t0 = time.time()
        while time.time() - t0 < wait:
            time.sleep(3)
            if time.time() - t0 > 10 and pg.evaluate(b.ANSWERS) > before and pg.evaluate(b.DONE):
                time.sleep(2)
                if pg.evaluate(b.DONE):     # a source chip with an attached file's name can trail the answer: dropped
                    names = {Path(f).name for f in attach}
                    lines = pg.evaluate(LAST_TEXT).splitlines()
                    return "\n".join(x for x in lines if x.strip() not in names).strip()
        raise b.fault(pg, n, "TIMEOUT", f"no finished answer after {wait} s")
    finally:
        if pg:
            pg.close()
        lock.unlink(missing_ok=True)


def free_first(accounts=ACCOUNTS):
    """Accounts with no live lock first, so a lone call does not wait behind a busy one."""
    def busy(n):
        f = HOME / f"acct{n}.busy"
        try:
            return f.exists() and driver().alive(int(f.read_text().strip() or 0))
        except (OSError, ValueError):
            return False
    return sorted(accounts, key=busy)


def ask(prompt, model="flash-lite", attach=(), wait=300, account=None):
    """(text, meta) with the first account that answers; text None when every account failed (meta["error"] says why,
    "no account ready" when none could take it). `account` = 1..4 or "acct<n>" to use only that one."""
    from playwright.sync_api import sync_playwright
    if account:
        order = [int(str(account).replace("acct", ""))]
    else:
        order = free_first()
    errors = []
    t0 = time.time()
    with sync_playwright() as pw:
        for n in order:
            try:
                text = ask_on(pw, n, prompt, attach, wait, model)
                return text, {"account": f"acct{n}", "model": model_name(model), "secs": round(time.time() - t0)}
            except Exception as e:  # noqa: BLE001 - sign-in, quota, not sent, timeout: the next account takes it
                errors.append(f"acct{n}: {str(e).splitlines()[0][:120]}")
    return None, {"error": "no account ready. " + "; ".join(errors)}


def status(max_age=600):
    """{"acct<n>": "signed in" | "needs sign-in (...)" | "never opened"}: the driver's cached status.json when it is
    fresh, else a live check (opens every profile)."""
    f = HOME / "status.json"
    if f.exists() and time.time() - f.stat().st_mtime < max_age:
        raw = json.loads(f.read_text(encoding="utf-8"))
    else:
        raw = driver().status()
    return {f"acct{k}": v for k, v in raw.items()}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    for k, v in status(max_age=0).items():
        print(k, v)
