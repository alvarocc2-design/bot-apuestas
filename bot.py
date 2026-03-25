import os
import time
import threading
import json
import urllib.request
import urllib.parse

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
ODDS_API_KEY = os.getenv("ODDS_API_KEY", "").strip()
API_FOOTBALL_KEY = os.getenv("API_FOOTBALL_KEY", "").strip()

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

def test_odds_api() -> str:
    if not ODDS_API_KEY:
        return "Falta ODDS_API_KEY"
    url = "https://api.the-odds-api.com/v4/sports"
    url += "?" + urllib.parse.urlencode({"apiKey": ODDS_API_KEY})
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
        if isinstance(data, list) and len(data) > 0:
            return f"ODDS API OK ✅ Deportes detectados: {len(data)}"
        return "ODDS API respondió, pero sin datos."
    except Exception as e:
        return f"ODDS API ERROR ❌ {e}"

def test_football_api() -> str:
    if not API_FOOTBALL_KEY:
        return "Falta API_FOOTBALL_KEY"
    url = "https://v3.football.api-sports.io/status"
    req = urllib.request.Request(url, method="GET")
    req.add_header("x-apisports-key", API_FOOTBALL_KEY)
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
        if data.get("response"):
            return "API-FOOTBALL OK ✅"
        return "API-FOOTBALL respondió, pero sin datos."
    except Exception as e:
        return f"API-FOOTBALL ERROR ❌ {e}"

def get_match_odds_message() -> str:
    try:
        url = "https://api.the-odds-api.com/v4/sports/soccer_spain_la_liga/events"
        url += "?" + urllib.parse.urlencode({"apiKey": ODDS_API_KEY})

        with urllib.request.urlopen(url, timeout=30) as response:
            events = json.loads(response.read().decode("utf-8"))

        if not events:
            return "No encontré eventos."

        event_id = events[0].get("id")
        home = events[0].get("home_team", "Local")
        away = events[0].get("away_team", "Visitante")

        odds_url = f"https://api.the-odds-api.com/v4/sports/soccer_spain_la_liga/events/{event_id}/odds"
        odds_url += "?" + urllib.parse.urlencode({
            "apiKey": ODDS_API_KEY,
            "regions": "us,us2",
            "markets": "player_shots,player_shots_on_target,player_to_receive_card",
            "oddsFormat": "decimal"
        })

        with urllib.request.urlopen(odds_url, timeout=30) as response:
            odds_data = json.loads(response.read().decode("utf-8"))

        bookmakers = odds_data.get("bookmakers", [])
        if not bookmakers:
            return f"No encontré cuotas para {home} vs {away}"

        mensaje = f"💰 Cuotas para:\n{home} vs {away}\n\n"

        found_any_player_market = False

        for book in bookmakers[:2]:
            mensaje += f"🏪 {book.get('title', 'Bookmaker')}\n"

            markets = book.get("markets", [])
            for market in markets:
                market_name = market.get("key")

                if market_name in ["player_shots", "player_shots_on_target", "player_to_receive_card"]:
                    outcomes = market.get("outcomes", [])
                    if outcomes:
                        found_any_player_market = True

                    for outcome in outcomes[:3]:
                        jugador = outcome.get("description") or outcome.get("name") or "Jugador"
                        cuota = outcome.get("price", "")
                        linea = outcome.get("point", "")

                        mensaje += f"{jugador} | {market_name} {linea} → {cuota}\n"

            mensaje += "\n"

        if not found_any_player_market:
            return f"No encontré mercados de jugador para {home} vs {away}"

        return mensaje

    except Exception as e:
        return f"Error cuotas ❌ {e}"

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
                    send_message("🤖 Bot conectado. Comandos: /ping /status /test_odds /test_football /liga /partidos /cuotas")
                elif text == "/ping":
                    send_message("pong 🟢")
                elif text == "/status":
                    send_message("Estado actual: bot estable, Telegram OK, modo seguro activado.")
                elif text == "/test_odds":
                    send_message(test_odds_api())
                elif text == "/test_football":
                    send_message(test_football_api())
                elif text == "/liga":
                    send_message("Comando /liga detectado ✅")
                elif text == "/partidos":
                    try:
                        url = "https://api.the-odds-api.com/v4/sports/soccer_spain_la_liga/events"
                        url += "?" + urllib.parse.urlencode({"apiKey": ODDS_API_KEY})

                        with urllib.request.urlopen(url, timeout=30) as response:
                            data_events = json.loads(response.read().decode("utf-8"))

                        if not data_events:
                            send_message("No hay partidos disponibles")
                            continue

                        mensaje = "📊 Próximos partidos:\n\n"
                        for partido in data_events[:5]:
                            home = partido.get("home_team", "Local")
                            away = partido.get("away_team", "Visitante")
                            mensaje += f"{home} vs {away}\n"

                        send_message(mensaje)

                    except Exception as e:
                        send_message(f"Error partidos ❌ {e}")
                elif text == "/cuotas":
                    send_message(get_match_odds_message())

        except Exception as e:
            print("command_loop error:", e)
            time.sleep(5)

def main():
    send_message("✅ Bot seguro activo en Railway")
    t1 = threading.Thread(target=heartbeat, daemon=True)
    t2 = threading.Thread(target=command_loop, daemon=True)
    t1.start()
    t2.start()

    while True:
        time.sleep(60)

if __name__ == "__main__":
    main()
