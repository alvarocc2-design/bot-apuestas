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

BANKROLL = 1000
MIN_EDGE = 0.08

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

def pick_stake(edge: float) -> float:
    if edge >= 0.15:
        return 25
    if edge >= 0.10:
        return 20
    return 15

def get_first_laliga_event():
    url = "https://api.the-odds-api.com/v4/sports/soccer_spain_la_liga/events"
    url += "?" + urllib.parse.urlencode({"apiKey": ODDS_API_KEY})

    with urllib.request.urlopen(url, timeout=30) as response:
        events = json.loads(response.read().decode("utf-8"))

    if not events:
        return None

    return events[0]

def get_event_odds(event_id: str):
    odds_url = f"https://api.the-odds-api.com/v4/sports/soccer_spain_la_liga/events/{event_id}/odds"
    odds_url += "?" + urllib.parse.urlencode({
        "apiKey": ODDS_API_KEY,
        "regions": "us,us2",
        "markets": "player_shots,player_shots_on_target,player_to_receive_card",
        "oddsFormat": "decimal"
    })

    with urllib.request.urlopen(odds_url, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))

def test_probability_from_odds(price: float) -> float:
    implied = 1 / price
    boosted = implied + 0.10
    return min(boosted, 0.85)

def get_player_id(name):
    simple_name = " ".join(name.split()[:2])

    url = "https://v3.football.api-sports.io/players"
    url += "?" + urllib.parse.urlencode({"search": simple_name})

    req = urllib.request.Request(url)
    req.add_header("x-apisports-key", API_FOOTBALL_KEY)

    with urllib.request.urlopen(req, timeout=30) as response:
        data = json.loads(response.read().decode("utf-8"))

    if data["response"]:
        return data["response"][0]["player"]["id"]

    return None

def get_player_stats(player_id):
    url = "https://v3.football.api-sports.io/players"
    url += "?" + urllib.parse.urlencode({
        "id": player_id,
        "season": 2024
    })

    req = urllib.request.Request(url)
    req.add_header("x-apisports-key", API_FOOTBALL_KEY)

    with urllib.request.urlopen(req, timeout=30) as response:
        data = json.loads(response.read().decode("utf-8"))

    try:
        stats = data["response"][0]["statistics"][0]["games"]["appearences"]
        return stats
    except:
        return None

def stats_command():
    try:
        event = get_first_laliga_event()
        if not event:
            return "No encontré eventos"

        event_id = event["id"]
        odds_data = get_event_odds(event_id)

        jugador = None
        for book in odds_data.get("bookmakers", []):
            for market in book.get("markets", []):
                if market.get("key") == "player_shots_on_target":
                    outcomes = market.get("outcomes", [])
                    if outcomes:
                        jugador = outcomes[0].get("description")
                        break
            if jugador:
                break

        if not jugador:
            return "No encontré jugador"

        player_id = get_player_id(jugador)
        if not player_id:
            return f"No encontré ID para {jugador}"

        stats = get_player_stats(player_id)

        return f"""📊 STATS REALES

Jugador: {jugador}
Partidos jugados: {stats}

⚠️ Próximo paso: tiros a puerta reales"""

    except Exception as e:
        return f"Error stats ❌ {e}"

def get_match_odds_message() -> str:
    try:
        event = get_first_laliga_event()
        if not event:
            return "No encontré eventos."

        event_id = event.get("id")
        home = event.get("home_team", "Local")
        away = event.get("away_team", "Visitante")

        odds_data = get_event_odds(event_id)

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

def get_value_message() -> str:
    try:
        event = get_first_laliga_event()
        if not event:
            return "No encontré eventos para analizar."

        event_id = event.get("id")
        home = event.get("home_team", "Local")
        away = event.get("away_team", "Visitante")

        odds_data = get_event_odds(event_id)
        bookmakers = odds_data.get("bookmakers", [])

        if not bookmakers:
            return f"No encontré cuotas para analizar en {home} vs {away}"

        checked = 0

        for book in bookmakers:
            book_name = book.get("title", "Bookmaker")
            for market in book.get("markets", []):
                market_name = market.get("key")

                if market_name != "player_shots_on_target":
                    continue

                for outcome in market.get("outcomes", []):
                    jugador = outcome.get("description") or outcome.get("name") or "Jugador"
                    price = outcome.get("price")
                    line = outcome.get("point", "")

                    if not isinstance(price, (int, float)):
                        continue

                    checked += 1
                    implied_prob = 1 / price
                    model_prob = test_probability_from_odds(price)
                    edge = (model_prob * price) - 1

                    if edge >= MIN_EDGE:
                        stake = pick_stake(edge)

                        return (
                            f"🔥 VALUE DETECTADO\n\n"
                            f"Partido: {home} vs {away}\n"
                            f"Casa: {book_name}\n\n"
                            f"Jugador: {jugador}\n"
                            f"Mercado: tiros a puerta\n"
                            f"Línea: {line}\n"
                            f"Cuota: {price}\n\n"
                            f"Prob. implícita: {implied_prob:.1%}\n"
                            f"Prob. estimada: {model_prob:.1%}\n"
                            f"Edge: {edge:.1%}\n\n"
                            f"Stake sugerido: {stake}€\n"
                            f"Bank: {BANKROLL}€\n\n"
                            f"⚠️ Este cálculo aún es de prueba. El siguiente paso será usar estadísticas reales."
                        )

        if checked == 0:
            return "No encontré props de tiros a puerta para analizar."
        return "He revisado props, pero no encontré value con el filtro actual."

    except Exception as e:
        return f"Error value ❌ {e}"

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
                    send_message("🤖 Bot conectado. Comandos: /ping /status /test_odds /test_football /liga /partidos /cuotas /value /stats")
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
                elif text == "/value":
                    send_message(get_value_message())
                elif text == "/stats":
                    send_message(stats_command())

        except Exception as e:
            print("command_loop error:", e)
            time.sleep(5)

def main():
    send_message("🔥 Bot PRO iniciando 🔥")
    t1 = threading.Thread(target=heartbeat, daemon=True)
    t2 = threading.Thread(target=command_loop, daemon=True)
    t1.start()
    t2.start()

    while True:
        time.sleep(60)

if __name__ == "__main__":
    main()
