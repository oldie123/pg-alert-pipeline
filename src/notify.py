"""Telegram delivery, with a stdout fallback so the demo runs without secrets."""
from __future__ import annotations

import json
import urllib.parse
import urllib.request

from .config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID


def send_message(text: str) -> bool:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print(f"[dry] {text}")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    body = urllib.parse.urlencode(
        {"chat_id": TELEGRAM_CHAT_ID, "text": text, "disable_web_page_preview": "true"}
    ).encode()
    req = urllib.request.Request(url, data=body, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read()).get("ok", False)
    except Exception as exc:  # network failures should not kill the evaluator
        print(f"[notify failed] {exc}")
        return False
