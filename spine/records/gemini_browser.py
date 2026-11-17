"""Gemini web in the owner's four signed-in Chrome profiles (no cookie files), for transcription.

Reuses tumrah-book's driver, `C:/Users/Ahmed/Desktop/tumrah-book/flow/images/browser.py`: profiles
~/.tumrah-chrome/acct1..4 (the owner signs in once with `py -m flow.images.browser login <n>` there), Chrome started
with --remote-debugging-port=934<n> and driven over CDP, model picked before every prompt, send retried until the box
empties, one process per account (acct<n>.busy). A profile on a sign-in page or a CAPTCHA is reported and skipped.

Here: one 5-minute audio piece is pasted into the prompt box as a file, with `gemini_run.PIECE_PROMPT`, on Flash-Lite
(the owner's transcription model). The answer's words come back as text.
"""
import base64
import sys
import time
from pathlib import Path

BOOK = Path(r"C:\Users\Ahmed\Desktop\tumrah-book")
MODEL = "Flash-Lite"


def driver():
    if str(BOOK) not in sys.path:
        sys.path.insert(0, str(BOOK))
    from flow.images import browser
    return browser


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
TYPES = {".ogg": "audio/ogg", ".m4a": "audio/mp4", ".mp3": "audio/mpeg", ".opus": "audio/ogg"}


def ask_audio(pw, n, prompt, audio, wait=300, model=MODEL):
    """Gemini's answer (text) to `prompt` with the audio file attached, on account n. Raises a named fault."""
    b = driver()
    lock = b.take(n)
    pg = None
    try:
        pg = b._open(pw, n, model)
        before = pg.evaluate(b.ANSWERS)
        pg.locator("div.ql-editor").first.fill(prompt)
        audio = Path(audio)
        pg.evaluate(PASTE_FILE, [base64.b64encode(audio.read_bytes()).decode(), audio.name,
                                 TYPES.get(audio.suffix.lower(), "audio/ogg")])
        time.sleep(3)
        b._send(pg, n)                                  # tried again every 4 s while the file uploads
        t0 = time.time()
        while time.time() - t0 < wait:
            time.sleep(3)
            if time.time() - t0 > 10 and pg.evaluate(b.ANSWERS) > before and pg.evaluate(b.DONE):
                time.sleep(2)
                if pg.evaluate(b.DONE):
                    return pg.evaluate(LAST_TEXT)
        raise b.fault(pg, n, "TIMEOUT", f"no finished answer after {wait} s")
    finally:
        if pg:
            pg.close()
        lock.unlink(missing_ok=True)


def status():
    return driver().status()
