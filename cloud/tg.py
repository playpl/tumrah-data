"""Telegram for the GitHub runner, and the one-time login on the PC that makes the runner's own session.

The runner never shares the PC's session file: one session used from two places at once can be killed by
Telegram (AUTH_KEY_DUPLICATED). So the runner gets a session of its own, made once on the PC:

    py -m cloud.tg login        (the owner runs it; Telegram sends a code to the account; the owner types it)

It writes %USERPROFILE%\\.tumrah-cloud\\telegram.txt with three lines: TG_API_ID, TG_API_HASH, TG_SESSION.
The owner pastes each into the GitHub repo's secrets (Settings > Secrets and variables > Actions), then deletes
the file. Nothing here prints a secret.
"""
import os
import sys
from pathlib import Path

TELEGRAM = Path(r"C:\Users\Ahmed\Desktop\tumrah\scripts\telegram")
OUT = Path.home() / ".tumrah-cloud" / "telegram.txt"


def on_runner():
    return bool(os.environ.get("TG_SESSION"))


async def connect():
    """An authorised client from TG_API_ID, TG_API_HASH, TG_SESSION (the runner's own session)."""
    from telethon import TelegramClient
    from telethon.sessions import StringSession
    client = TelegramClient(StringSession(os.environ["TG_SESSION"]), int(os.environ["TG_API_ID"]),
                            os.environ["TG_API_HASH"])
    await client.connect()
    if not await client.is_user_authorized():
        await client.disconnect()
        raise RuntimeError("the runner's Telegram session needs a new login: run `py -m cloud.tg login` on the PC")
    return client


def login():
    """Interactive, on the PC: a new session (its own auth key) for the runner."""
    import asyncio
    sys.path[:0] = [str(TELEGRAM / "quizbot"), str(TELEGRAM)]
    from reveal_keys_round3 import load_credentials
    from telethon import TelegramClient
    from telethon.sessions import StringSession
    api_id, api_hash = load_credentials()

    async def go():
        client = TelegramClient(StringSession(), int(api_id), str(api_hash), device_model="tumrah-data runner")
        await client.start()          # asks for the phone number and the code in this terminal
        s = client.session.save()
        await client.disconnect()
        return s

    session = asyncio.run(go())
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(f"TG_API_ID={api_id}\nTG_API_HASH={api_hash}\nTG_SESSION={session}\n", encoding="utf-8")
    print(f"written: {OUT}\nPaste the three values into the GitHub repo's Actions secrets, then delete the file.")


if __name__ == "__main__":
    if sys.argv[1:] == ["login"]:
        login()
    else:
        print(__doc__)
