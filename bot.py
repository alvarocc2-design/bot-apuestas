import os
import time
import requests

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
    data = {
        "chat_id": CHAT_ID,
        "text": text,
    }

    response = requests.post(url, data=data, timeout=30)
    print("Telegram status:", response.status_code)
    print("Telegram response:", response.text)
    response.raise_for_status()

def main() -> None:
    send_message("🔥 Bot funcionando correctamente en Railway 🔥")
    while True:
        time.sleep(300)
        send_message("Sigo activo ✅")

if __name__ == "__main__":
    main()
