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
    py gemini_browser.py limits [model] which accounts have the model now, and when a capped one renews

A model at its usage cap is not in the mode menu: its option reads "usage cap renews on 18 Nov, 4:53 AM". `ask` then
raises Capped, writes `acct<n>.cap.<model>` (epoch of the renewal) and skips that account until then; when every
account is capped, meta["until"] is the first renewal (callers may wait for it).

`ask(prompt, model, attach, wait)` -> (text or None, meta): attachments (audio, PDF, text, pictures) are pasted into
the prompt box as files, the answer's body is read as text.
"""
import base64
import json
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

BOOK = Path(r"C:\Users\Ahmed\Desktop\tumrah-book")
HOME = Path.home() / ".tumrah-chrome"
ACCOUNTS = (1, 2, 3, 4)
# The owner's names -> the text of Gemini's mode menu option (the option holds the model's Latin name in every UI language).
MODELS = {"flash-lite": "Flash-Lite", "gemini-flash-lite": "Flash-Lite", "flash": "Flash", "gemini-flash": "Flash",
          "hydrogen": "Hydrogen"}
# A capped account answers with its free model until the renewal (owner, 2026-11-20).
FALLBACK = {"hydrogen": "flash-lite"}
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


class Capped(RuntimeError):
    """The account cannot use the model until `until` (epoch seconds)."""
    def __init__(self, n, model, until):
        super().__init__(f"account {n}: {model} at its usage cap until "
                         + time.strftime("%d %b %H:%M", time.localtime(until)))
        self.until = until


_DIGITS = {0x660 + i: str(i) for i in range(10)} | {0x6F0 + i: str(i) for i in range(10)}
_AMPM = r"(\u0635|\u0645|AM|PM|am|pm)?"           # ص = AM, م = PM
_RENEW_DAY = re.compile(r"(\d{1,2})\D{0,20}?[,\u060c]\s*(\d{1,2}):(\d{2})\s*" + _AMPM)
_RENEW_TIME = re.compile(r"(\d{1,2}):(\d{2})\s*" + _AMPM)


def renews_at(text, now=None):
    """Epoch seconds of the renewal a capped option names ("... ١٨ نوفمبر، ٤:٥٣ ص", "... Nov 18, 4:53 AM"), or None."""
    t = (text or "").translate(_DIGITS)
    m = _RENEW_DAY.search(t)
    if m:
        day, h, mi, ap = int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4)
    else:
        m = _RENEW_TIME.search(t)
        if not m:
            return None
        day, h, mi, ap = None, int(m.group(1)), int(m.group(2)), m.group(3)
    if ap in ("\u0645", "PM", "pm") and h < 12:
        h += 12
    if ap in ("\u0635", "AM", "am") and h == 12:
        h = 0
    now = now or datetime.now()
    when = now.replace(hour=h, minute=mi, second=0, microsecond=0)
    if day is not None:
        try:
            when = when.replace(day=day)
        except ValueError:
            pass
        if when < now - timedelta(days=2):                 # the renewal falls in next month
            when = (when.replace(day=1) + timedelta(days=32)).replace(day=day)
    elif when < now:
        when += timedelta(days=1)
    return when.timestamp()


def _cap_file(n, model):
    return HOME / f"acct{n}.cap.{model_name(model).lower()}"


def capped_until(n, model):
    """Epoch of the renewal when account n is known to be capped for the model now, else None."""
    try:
        until = float(_cap_file(n, model).read_text().strip())
    except (OSError, ValueError):
        return None
    return until if until > time.time() else None


def _menu(pg):
    """[option text] of Gemini's mode menu (opened, read, closed)."""
    btn = pg.locator('[data-test-id="bard-mode-menu-button"]').first
    btn.wait_for(timeout=15000)
    btn.click()
    time.sleep(1.5)
    opts = [o.inner_text().strip() for o in pg.locator('[data-test-id^="bard-mode-option"]').all()]
    pg.keyboard.press("Escape")
    return opts


def cap_of(pg, model):
    """Epoch of the renewal when the model is missing from the menu and an option names a renewal, else None."""
    opts = _menu(pg)
    name = model_name(model).lower()
    if any(name in o.lower() for o in opts):
        return None
    times = [t for t in (renews_at(o) for o in opts) if t]
    return min(times) if times else None


def limits(model="hydrogen"):
    """{"acct<n>": "ready" | "capped until <time>" | error}: opens each profile's mode menu."""
    from playwright.sync_api import sync_playwright
    b, out = driver(), {}
    with sync_playwright() as pw:
        for n in ACCOUNTS:
            lock, pg = b.take(n), None
            try:
                pg = b.page(pw, n)
                until = cap_of(pg, model)
                if until:
                    _cap_file(n, model).write_text(str(until))
                    out[f"acct{n}"] = "capped until " + time.strftime("%d %b %H:%M", time.localtime(until))
                else:
                    _cap_file(n, model).unlink(missing_ok=True)
                    out[f"acct{n}"] = "ready"
            except Exception as e:  # noqa: BLE001
                out[f"acct{n}"] = str(e).splitlines()[0][:120]
            finally:
                if pg:
                    pg.close()
                lock.unlink(missing_ok=True)
    return out


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
        pg = b.page(pw, n)
        _open(b, pg, n, model)
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


def ask_on_fallback(pw, n, prompt, attach=(), wait=300, model="hydrogen"):
    """ask_on with the owner's cap rule (2026-11-20): when account n is capped for `model` (known, or found now) it
    answers with FALLBACK[model] until the renewal. Returns (text, model name that answered)."""
    alt = FALLBACK.get((model or "").lower())
    if alt and capped_until(n, model):
        return ask_on(pw, n, prompt, attach, wait, alt), model_name(alt)
    try:
        return ask_on(pw, n, prompt, attach, wait, model), model_name(model)
    except Capped:
        if not alt:
            raise
        return ask_on(pw, n, prompt, attach, wait, alt), model_name(alt)


def _open(b, pg, n, model):
    """The driver's _open on a page already open: signed in, then the model; a model at its cap raises Capped."""
    if not b.signed_in(pg):
        raise b.fault(pg, n, "SIGN-IN", f"py -m flow.images.browser login {n}")
    try:
        b.pick_model(pg, n, model_name(model))
    except Exception:
        until = cap_of(pg, model)
        if until:
            _cap_file(n, model).write_text(str(until))
            raise Capped(n, model_name(model), until) from None
        raise
    _cap_file(n, model).unlink(missing_ok=True)


def free_first(accounts=ACCOUNTS):
    """Accounts with no live lock first, so a lone call does not wait behind a busy one."""
    def busy(n):
        f = HOME / f"acct{n}.busy"
        try:
            return f.exists() and driver().alive(int(f.read_text().strip() or 0))
        except (OSError, ValueError):
            return False
    return sorted(accounts, key=busy)


def ask(prompt, model="flash-lite", attach=(), wait=300, account=None, fallback=True):
    """(text, meta) with the first account that answers; text None when every account failed (meta["error"] says why,
    "no account ready" when none could take it). `account` = 1..4 or "acct<n>" to use only that one.

    Owner, 2026-11-20: "use hydrogen; when [it] hit cap on an acc use the free model till reset". An account whose
    model is capped answers with FALLBACK[model] (Hydrogen -> Flash-Lite) until its renewal; meta["model"] names the
    model that answered and meta["fallback"] is True then. `fallback=False` keeps the old wait-for-renewal behaviour."""
    from playwright.sync_api import sync_playwright
    if account:
        order = [int(str(account).replace("acct", ""))]
    else:
        order = free_first()
    alt = FALLBACK.get((model or "").lower()) if fallback else None
    caps = {n: capped_until(n, model) for n in order}
    # accounts with the model first; a capped account still answers with the fallback model, after them
    tries = [(n, model) for n in order if not caps[n]] + ([(n, alt) for n in order if caps[n]] if alt else [])
    errors = [f"acct{n}: capped" for n, u in caps.items() if u and not alt]
    t0 = time.time()
    with sync_playwright() as pw:
        i = 0
        while i < len(tries):
            n, m = tries[i]
            i += 1
            try:
                text = ask_on(pw, n, prompt, attach, wait, m)
                return text, {"account": f"acct{n}", "model": model_name(m), "secs": round(time.time() - t0),
                              **({"fallback": True} if m != model else {})}
            except Capped as e:
                if m == model:
                    caps[n] = e.until
                    if alt:
                        tries.append((n, alt))          # capped just now: this account answers with the fallback
                errors.append(f"acct{n}: {e}")
            except Exception as e:  # noqa: BLE001 - sign-in, not sent, timeout: the next account takes it
                errors.append(f"acct{n}: {str(e).splitlines()[0][:120]}")
    meta = {"error": "no account ready. " + "; ".join(errors)}
    if caps and all(caps.values()):
        meta["until"] = min(caps.values())          # every account is capped for this model: the first renewal
    return None, meta


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
    if sys.argv[1:2] == ["limits"]:
        for k, v in limits(*(sys.argv[2:3] or ["hydrogen"])).items():
            print(k, v)
    else:
        for k, v in status(max_age=0).items():
            print(k, v)
