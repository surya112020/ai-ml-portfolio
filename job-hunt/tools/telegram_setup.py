"""Find your Telegram chat id and verify the bot works.

    1. In Telegram, message @BotFather -> /newbot -> copy the token
    2. Send any message ("hi") to your new bot
    3. python3 tools/telegram_setup.py <token>

Prints the chat id and sends a test message. Put both values in .env:

    TELEGRAM_BOT_TOKEN=...
    TELEGRAM_CHAT_ID=...
"""

from __future__ import annotations

import sys
from pathlib import Path

import requests


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    token = sys.argv[1].strip()

    resp = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=20)
    if resp.status_code != 200:
        print(f"bad token — getMe returned {resp.status_code}: {resp.text[:200]}")
        return 1
    bot = resp.json()["result"]
    print(f"bot ok: @{bot['username']}")

    resp = requests.get(f"https://api.telegram.org/bot{token}/getUpdates", timeout=20)
    updates = resp.json().get("result", [])
    chats = {}
    for update in updates:
        message = update.get("message") or update.get("channel_post") or {}
        chat = message.get("chat") or {}
        if chat.get("id"):
            name = chat.get("username") or chat.get("first_name") or chat.get("title")
            chats[chat["id"]] = name

    if not chats:
        print(
            f"\nNo messages found yet.\n\n"
            f"  1. Open Telegram and search for @{bot['username']}\n"
            f"  2. Press Start, then send it any message (e.g. 'hi')\n"
            f"  3. Re-run this exact command\n\n"
            f"getUpdates only returns chats that have messaged the bot, so\n"
            f"this step cannot be skipped."
        )
        return 1

    for chat_id, name in chats.items():
        print(f"  chat_id={chat_id}  ({name})")

    chat_id = next(iter(chats))
    requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": "jobhunt is wired up ✅"},
        timeout=20,
    )
    print(f"\nTest message sent to {chat_id} — check Telegram.")

    # Write .env directly; copying two lines by hand is a step people skip.
    env_path = Path(__file__).resolve().parent.parent / ".env"
    existing = {}
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                key, _, value = line.partition("=")
                existing[key.strip()] = value.strip()
    existing["TELEGRAM_BOT_TOKEN"] = token
    existing["TELEGRAM_CHAT_ID"] = str(chat_id)
    env_path.write_text(
        "\n".join(f"{k}={v}" for k, v in sorted(existing.items())) + "\n"
    )
    env_path.chmod(0o600)
    print(f"Wrote {env_path} (gitignored, chmod 600).")
    print("\nNow run:  ./.venv/bin/python -m jobhunt test-alert")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
