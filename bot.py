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

# 🔥 FIX IMPORTANTE (búsqueda de jugador mejorada)
def get_player_id(name):
    posibles_busquedas = [
        name,
        " ".join(name.split()[:2]),
        name.split()[-1]
    ]

    for busqueda in posibles_busquedas:
        try:
            url = "https://v3.football.api-sports.io/players"
            url += "?" + urllib.parse.urlencode({"search": busqueda})

            req = urllib.request.Request(url)
            req.add_header("x-apisports-key", API_FOOTBALL_KEY)

            with urllib.request.urlopen(req, timeout=30) as response:
                data = json.loads(response.read().decode("utf-8"))

            if data["response"]:
                return data["response"][0]["player"]["id"]

        except:
            continue

    return None

def get_player_stats(player_name):
    player_id = get_player_id(player_name)
    if not player_id:
        return f"No encontré ID para {player_name}"

    try:
        url = "https://v3.football.api-sports.io/players"
        url += "?" + urllib.parse.urlencode({"id": player_id, "season": 2024})

        req = urllib.request.Request(url)
        req.add_header("x-apisports-key", API_FOOTBALL_KEY)

        with urllib.request.urlopen(req, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))

        stats = data["response"][0]["statistics"][0]

        tiros = stats["shots"]["total"] or 0
        tiros_puerta = stats["shots"]["on"] or 0
        partidos = stats["games"]["appearences"] or 1

        media = round(tiros_puerta / partidos, 2)

        return f"""📊 Stats {player_name}

Partidos: {partidos}
Tiros totales: {tiros}
Tiros a puerta: {tiros_puerta}
Media tiros a puerta: {media}
"""

    except Exception as e:
        return f"Error stats ❌ {e}"

def get_match_odds_message() -> str:
    try:
        url = "https://api.the-odds-api.com/v4/sports/soccer_spain_la_liga/events"
        url += "?" + urllib.parse.urlencode({"apiKey": ODDS_API_KEY})

        with urllib.request.urlopen(url, timeout=30) as response:
            events = json.loads(response.read().decode("utf-8"))

        if not events:
            return "No encontré eventos."

        event_id = events[0]["id"]
        home = events[0]["home_team"]
        away = events[0]["away_team"]

        odds_url = f"https://api.the-odds-api.com/v4/sports/soccer_spain_la_liga/events/{event_id}/odds"
        odds_url += "?" + urllib.parse.urlencode({
            "apiKey": ODDS_API_KEY,
            "regions": "us,us2",
            "markets": "player_shots_on_target",
            "oddsFormat": "decimal"
        })

        with urllib.request.urlopen(odds_url, timeout=30) as response:
            odds_data = json.loads(response.read().decode("utf-8"))

        bookmakers = odds_data.get("bookmakers", [])
        if not bookmakers:
            return "No hay cuotas disponibles."

        mensaje = f"💰 Cuotas para:\n{home} vs {away}\n\n"

        for book in bookmakers[:2]:
            mensaje += f"🏪 {book['title']}\n"

            for market in book["markets"]:
                for outcome in market["outcomes"][:3]:
                    jugador = outcome["description"]
                    linea = outcome["point"]
                    cuota = outcome["price"]

                    mensaje += f"{jugador} → {cuota}\n"

            mensaje += "\n"

        return mensaje

    except Exception as e:
        return f"Error cuotas ❌ {e}"

def detect_value():
    try:
        url = "https://api.the-odds-api.com/v4/sports/soccer_spain_la_liga/events"
        url += "?" + urllib.parse.urlencode({"apiKey": ODDS_API_KEY})

        with urllib.request.urlopen(url, timeout=30) as response:
            events = json.loads(response.read().decode("utf-8"))

        event = events[0]
        event_id = event["id"]
        home = event["home_team"]
        away = event["away_team"]

        odds_url = f"https://api.the-odds-api.com/v4/sports/soccer_spain_la_liga/events/{event_id}/odds"
        odds_url += "?" + urllib.parse.urlencode({
            "apiKey": ODDS_API_KEY,
            "regions": "us,us2",
            "markets": "player_shots_on_target",
            "oddsFormat": "decimal"
        })

        with urllib.request.urlopen(odds_url, timeout=30) as response:
            odds_data = json.loads(response.read().decode("utf-8"))

        book = odds_data["bookmakers"][0]
        market = book["markets"][0]
        outcome = market["outcomes"][0]

        jugador = outcome["description"]
        cuota = outcome["price"]

        prob_implicita = round(1 / cuota * 100, 1)
        prob_estimada = prob_implicita + 10

        return f"""🔥 VALUE DETECTADO

{home} vs {away}

Jugador: {jugador}
Cuota: {cuota}

Prob implícita: {prob_implicita}%
Prob estimada: {prob_estimada}%
"""

    except Exception as e:
        return f"Error value ❌ {e}"

def command_loop():
    offset = None
    while True:
        try:
            data = get_updates(offset)

            for item in data.get("result", []):
                offset = item["update_id"] + 1
                text = item["message"].get("text", "")

                if text == "/start":
                    send_message("🤖 Bot PRO activo\nComandos: /cuotas /value /stats")

                elif text == "/cuotas":
                    send_message(get_match_odds_message())

                elif text == "/value":
                    send_message(detect_value())

                elif text == "/stats":
                    send_message(get_player_stats("Aleix Febas"))

        except Exception as e:
            print(e)
            time.sleep(5)

def main():
    send_message("🔥 Bot PRO iniciando 🔥")

    t = threading.Thread(target=command_loop)
    t.start()

    while True:
        time.sleep(60)

if __name__ == "__main__":
    main()
