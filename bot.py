import os
import time
import threading
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
        print("send_message:", body)

def get_updates(offset=None):
    url = f"https://api.telegram.org/bot{TOKEN}/getUpdates"
    params = {}
    if offset is not None:
        params["offset"] = offset
    full_url = url
    if params:
        full_url += "?" + urllib.parse.urlencode(params)

    with urllib.request.urlopen(full_url, timeout=30) as response:
        body = response.read().decode("utf-8")
        return body

def send_startup_message():
    send_message("✅ Bot seguro activo en Railway")

def heartbeat():
    while True:
        try:
            time.sleep(300)
            send_message("Sigo activo ✅")
        except Exception as e:
            print("heartbeat error:", e)
            time.sleep(30)

def command_loop():
    offset = None
    while True:
        try:
            raw = get_updates(offset)
            print("updates:", raw)

            import json
            data = json.loads(raw)

            if not data.get("ok"):
                time.sleep(5)
                continue

            for item in data.get("result", []):
                update_id = item["update_id"]
                offset = update_id + 1

                message = item.get("message", {})
                text = message.get("text", "")

                if text == "/start":
                    send_message("🤖 Bot conectado. Comandos disponibles: /start, /ping, /status")
                elif text == "/ping":
                    send_message("pong 🟢")
                elif text == "/status":
                    send_message("Estado actual: bot estable, Telegram OK, modo seguro activado.")
        except Exception as e:
            print("command_loop error:", e)
            time.sleep(5)

def main():
    send_startup_message()

    t1 = threading.Thread(target=heartbeat, daemon=True)
    t2 = threading.Thread(target=command_loop, daemon=True)

    t1.start()
    t2.start()

    while True:
        time.sleep(60)

if __name__ == "__main__":
    main()
