import os
import time
import json
import urllib.request
import urllib.parse

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

def send_message(text: str) -> None:
    if not TOKEN:
        print("ERROR: falta TELEGRAM_BOT_TOKEN")
        return
    if not CHAT_ID:
        print("ERROR: falta TELEGRAM_CHAT_ID")
        return

    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": CHAT_ID,
        "text": text,
    }).encode("utf-8")

    req = urllib.request.Request(url, data=data, method="POST")
    with urllib.request.urlopen(req, timeout=30) as response:
        body = response.read().decode("utf-8")
        print("Telegram response:", body)

def main() -> None:
    send_message("🔥 Bot funcionando correctamente en Railway 🔥")
    while True:
        time.sleep(300)
        send_message("Sigo activo ✅")

if __name__ == "__main__":
    main()
