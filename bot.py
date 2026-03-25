import os
import time
import threading
import json
import urllib.request
import urllib.parse

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
ODDS_API_KEY = os.getenv("ODDS_API_KEY", "").strip()

# Configuración
MIN_EDGE = 0.05
MAX_LINE = 11.5
PREFERRED_LINES = [8.5, 9.5, 10.5, 11.5]

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

    with urllib.request.urlopen(url, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))

def estimate_probability(line, price, market_type):
    """
    Modelo simple pero más sensato:
    - parte de la probabilidad implícita
    - ajusta según la línea
    - ajusta según si es Over o Under
    """
    implied = 1 / price
    estimated = implied + 0.04

    # Preferimos líneas razonables
    if line <= 8.5:
        if market_type == "Over":
            estimated += 0.03
        else:
            estimated -= 0.02
    elif line == 9.5:
        estimated += 0.02
    elif line == 10.5:
        estimated += 0.00
    elif line == 11.5:
        if market_type == "Over":
            estimated -= 0.04
        else:
            estimated += 0.03
    else:
        # Penalizamos líneas raras
        estimated -= 0.03

    estimated = max(0.08, min(estimated, 0.82))
    return estimated

def line_priority_score(line):
    if line == 9.5:
        return 5
    if line == 10.5:
        return 4
    if line == 8.5:
        return 3
    if line == 11.5:
        return 2
    return 0

def suggested_stake(edge):
    if edge >= 0.15:
        return 25
    if edge >= 0.10:
        return 20
    return 15

def get_corners_value_message():
    try:
        event = get_first_event()
        if not event:
            return "No encontré eventos"

        home = event.get("home_team", "Local")
        away = event.get("away_team", "Visitante")

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
                    market_type = outcome.get("name")  # Over o Under

                    if market_type not in ["Over", "Under"]:
                        continue

                    line = outcome.get("point")
                    price = outcome.get("price")

                    if not isinstance(price, (int, float)) or line is None:
                        continue

                    try:
                        line = float(line)
                    except Exception:
                        continue

                    if line > MAX_LINE or line not in PREFERRED_LINES:
                        continue

                    implied = 1 / price
                    estimated = estimate_probability(line, price, market_type)
                    edge = (estimated * price) - 1
                    priority = line_priority_score(line)

                    if edge < MIN_EDGE:
                        continue

                    candidate = {
                        "book": book_name,
                        "type": market_type,
                        "line": line,
                        "price": price,
                        "edge": edge,
                        "implied": implied,
                        "estimated": estimated,
                        "priority": priority
                    }

                    if best_pick is None:
                        best_pick = candidate
                    else:
                        # Primero priorizamos líneas mejores, luego edge
                        if (
                            candidate["priority"] > best_pick["priority"]
                            or (
                                candidate["priority"] == best_pick["priority"]
                                and candidate["edge"] > best_pick["edge"]
                            )
                        ):
                            best_pick = candidate

        if not best_pick:
            return "No encontré value ahora mismo"

        stake = suggested_stake(best_pick["edge"])

        return (
            f"🔥 VALUE DETECTADO\n\n"
            f"Partido: {home} vs {away}\n"
            f"Casa: {best_pick['book']}\n\n"
            f"Mercado: {best_pick['type']} córners\n"
            f"Línea: {best_pick['line']}\n"
            f"Cuota: {best_pick['price']}\n\n"
            f"Prob. implícita: {best_pick['implied']:.1%}\n"
            f"Prob. estimada: {best_pick['estimated']:.1%}\n"
            f"Edge: {best_pick['edge']:.1%}\n\n"
            f"Stake: {stake}€\n\n"
            f"⚠️ Modelo basado solo en cuotas"
        )

    except Exception as e:
        return f"Error ❌ {e}"

def get_corners_odds_message():
    try:
        event = get_first_event()
        if not event:
            return "No encontré eventos"

        home = event.get("home_team", "Local")
        away = event.get("away_team", "Visitante")

        odds_data = get_event_odds(event.get("id"))
        bookmakers = odds_data.get("bookmakers", [])

        if not bookmakers:
            return "No hay cuotas disponibles"

        mensaje = f"🚩 Cuotas de córners\n\n{home} vs {away}\n\n"

        found = False

        for book in bookmakers[:3]:
            mensaje += f"🏪 {book.get('title', 'Bookmaker')}\n"

            for market in book.get("markets", []):
                if market.get("key") != "alternate_totals_corners":
                    continue

                for outcome in market.get("outcomes", []):
                    name = outcome.get("name")
                    point = outcome.get("point")
                    price = outcome.get("price")

                    try:
                        point = float(point)
                    except Exception:
                        continue

                    if point in PREFERRED_LINES and name in ["Over", "Under"]:
                        found = True
                        mensaje += f"{name} {point} → {price}\n"

            mensaje += "\n"

        if not found:
            return "No encontré líneas útiles de córners"

        return mensaje

    except Exception as e:
        return f"Error cuotas ❌ {e}"

def heartbeat():
    while True:
        try:
            time.sleep(300)
            send_message("Sigo activo ✅")
        except Exception:
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
                    send_message(
                        "🤖 Bot listo.\n"
                        "Comandos:\n"
                        "/ping\n"
                        "/corners_cuotas\n"
                        "/corners_value"
                    )

                elif text == "/ping":
                    send_message("pong 🟢")

                elif text == "/corners_cuotas":
                    send_message(get_corners_odds_message())

                elif text == "/corners_value":
                    send_message(get_corners_value_message())

        except Exception as e:
            print("loop error:", e)
            time.sleep(5)

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
