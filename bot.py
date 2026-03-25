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

def get_first_player():
    url = "https://api.the-odds-api.com/v4/sports/soccer_spain_la_liga/events"
    url += "?" + urllib.parse.urlencode({"apiKey": ODDS_API_KEY})

    with urllib.request.urlopen(url, timeout=30) as response:
        events = json.loads(response.read().decode("utf-8"))

    event = events[0]
    event_id = event["id"]

    odds_url = f"https://api.the-odds-api.com/v4/sports/soccer_spain_la_liga/events/{event_id}/odds"
    odds_url += "?" + urllib.parse.urlencode({
        "apiKey": ODDS_API_KEY,
        "regions": "us",
        "markets": "player_shots_on_target"
    })

    with urllib.request.urlopen(odds_url, timeout=30) as response:
        odds = json.loads(response.read().decode("utf-8"))

    for book in odds.get("bookmakers", []):
        for market in book.get("markets", []):
            for outcome in market.get("outcomes", []):
                return outcome.get("description")

    return None

def get_player_id(name):
    url = "https://v3.football.api-sports.io/players"
    url += "?" + urllib.parse.urlencode({"search": name})

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
        jugador = get_first_player()
        if not jugador:
            return "No encontré jugador"

        player_id = get_player_id(jugador)
        if not player_id:
            return f"No encontré ID para {jugador}"

        stats = get_player_stats(player_id)

        return f"""
📊 STATS REALES

Jugador: {jugador}
Partidos jugados: {stats}

⚠️ Próximo paso: tiros a puerta reales
"""
    except Exception as e:
        return f"Error stats ❌ {e}"

def heartbeat():
    while True:
        time.sleep(300)
        send_message("Sigo activo ✅")

def command_loop():
    offset = None
    while True:
        try:
            data = get_updates(offset)

            for item in data.get("result", []):
                offset = item["update_id"] + 1
                text = item.get("message", {}).get("text", "")

                if text == "/stats":
                    send_message(stats_command())
                elif text == "/start":
                    send_message("Bot activo")
        except:
            time.sleep(5)

def main():
    send_message("🔥 Bot PRO iniciando 🔥")

    threading.Thread(target=heartbeat, daemon=True).start()
    threading.Thread(target=command_loop, daemon=True).start()

    while True:
        time.sleep(60)

if __name__ == "__main__":
    main()
