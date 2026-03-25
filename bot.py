import os
import time
import threading
import json
import urllib.request
import urllib.parse

# ==============================
# VARIABLES
# ==============================

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
ODDS_API_KEY = os.getenv("ODDS_API_KEY", "").strip()

# ==============================
# TELEGRAM
# ==============================

def send_message(text: str) -> None:
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": CHAT_ID,
        "text": text,
    }).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    with urllib.request.urlopen(req, timeout=30) as response:
        print(response.read().decode("utf-8"))

def get_updates(offset=None):
    url = f"https://api.telegram.org/bot{TOKEN}/getUpdates"
    if offset is not None:
        url += "?" + urllib.parse.urlencode({"offset": offset})
    with urllib.request.urlopen(url, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))

# ==============================
# ODDS API
# ==============================

def get_first_event():
    url = "https://api.the-odds-api.com/v4/sports/soccer_spain_la_liga/events"
    url += "?" + urllib.parse.urlencode({"apiKey": ODDS_API_KEY})

    with urllib.request.urlopen(url, timeout=30) as response:
        events = json.loads(response.read().decode("utf-8"))

    if not events:
        return None

    return events[0]

def get_event_odds(event_id):
    url = f"https://api.the-odds-api.com/v4/sports/soccer_spain_la_liga/events/{event_id}/odds"
    url += "?" + urllib.parse.urlencode({
        "apiKey": ODDS_API_KEY,
        "regions": "eu,uk,us",
        "markets": "alternate_totals_corners",
        "oddsFormat": "decimal"
    })

    req = urllib.request.Request(url, method="GET")

    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))

# ==============================
# VALUE CÓRNERS (SIN BLOQUEOS)
# ==============================

def get_corners_value_message():
    try:
        event = get_first_event()
        if not event:
            return "No encontré eventos"

        home = event.get("home_team")
        away = event.get("away_team")

        odds_data = get_event_odds(event.get("id"))
        bookmakers = odds_data.get("bookmakers", [])

        if not bookmakers:
            return "No hay cuotas disponibles"

        best_pick = None

        for book in bookmakers:
            book_name = book.get("title", "Bookmaker")

            for market in book.get("markets", []):
                if market.get("key") != "alternate_totals_corners":
                    continue

                for outcome in market.get("outcomes", []):
                    if outcome.get("name") != "Over":
                        continue

                    line = outcome.get("point")
                    price = outcome.get("price")

                    if not isinstance(price, (int, float)) or line is None:
                        continue

                    implied = 1 / price

                    # 🔥 MODELO SIMPLE (estable)
                    estimated = min(implied + 0.08, 0.85)

                    edge = (estimated * price) - 1

                    if edge > 0.05:
                        candidate = {
                            "book": book_name,
                            "line": line,
                            "price": price,
                            "edge": edge,
                            "implied": implied,
                            "estimated": estimated
                        }

                        if not best_pick or candidate["edge"] > best_pick["edge"]:
                            best_pick = candidate

        if not best_pick:
            return "No encontré value ahora mismo"

        stake = 20

        return (
            f"🔥 VALUE DETECTADO\n\n"
            f"Partido: {home} vs {away}\n"
            f"Casa: {best_pick['book']}\n\n"
            f"Mercado: Over córners\n"
            f"Línea: {best_pick['line']}\n"
            f"Cuota: {best_pick['price']}\n\n"
            f"Prob. implícita: {best_pick['implied']:.1%}\n"
            f"Prob. estimada: {best_pick['estimated']:.1%}\n"
            f"Edge: {best_pick['edge']:.1%}\n\n"
            f"Stake: {stake}€"
        )

    except Exception as e:
        return f"Error ❌ {e}"

# ==============================
# LOOP BOT
# ==============================

def heartbeat():
    while True:
        try:
            time.sleep(300)
            send_message("Sigo activo ✅")
        except:
            time.sleep(30)

def command_loop():
    offset = None
    while True:
        try:
            data = get_updates(offset)

            if not data.get("ok"):
                time.sleep(5)
                continue

            for item in data.get("result", []):
                update_id = item["update_id"]
                offset = update_id + 1

                message = item.get("message", {})
                text = message.get("text", "")

                if text == "/start":
                    send_message("🤖 Bot listo. Usa /corners_value")

                elif text == "/ping":
                    send_message("pong 🟢")

                elif text == "/corners_value":
                    send_message(get_corners_value_message())

        except Exception as e:
            print("loop error:", e)
            time.sleep(5)

# ==============================
# MAIN
# ==============================

def main():
    send_message("🔥 Bot PRO córners iniciado 🔥")

    t1 = threading.Thread(target=heartbeat, daemon=True)
    t2 = threading.Thread(target=command_loop, daemon=True)

    t1.start()
    t2.start()

    while True:
        time.sleep(60)

if __name__ == "__main__":
    main()
