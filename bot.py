import os
import time
import threading
import json
import urllib.request
import urllib.parse
import unicodedata

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
ODDS_API_KEY = os.getenv("ODDS_API_KEY", "").strip()
API_FOOTBALL_KEY = os.getenv("API_FOOTBALL_KEY", "").strip()

BANKROLL = 1000
MIN_EDGE = 0.08
LEAGUE_ID = 140   # La Liga
SEASON = 2024     # ajusta si hace falta

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

def normalize_text(text: str) -> str:
    text = (text or "").lower().strip()
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = text.replace(".", " ").replace("-", " ").replace("'", " ")
    return " ".join(text.split())

def football_get(path: str, params: dict):
    url = f"https://v3.football.api-sports.io{path}"
    url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, method="GET")
    req.add_header("x-apisports-key", API_FOOTBALL_KEY)
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))

def odds_get(path: str, params: dict):
    url = f"https://api.the-odds-api.com/v4{path}"
    url += "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))

def test_odds_api() -> str:
    if not ODDS_API_KEY:
        return "Falta ODDS_API_KEY"
    try:
        data = odds_get("/sports", {"apiKey": ODDS_API_KEY})
        if isinstance(data, list) and len(data) > 0:
            return f"ODDS API OK ✅ Deportes detectados: {len(data)}"
        return "ODDS API respondió, pero sin datos."
    except Exception as e:
        return f"ODDS API ERROR ❌ {e}"

def test_football_api() -> str:
    if not API_FOOTBALL_KEY:
        return "Falta API_FOOTBALL_KEY"
    try:
        data = football_get("/status", {})
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
    events = odds_get(
        "/sports/soccer_spain_la_liga/events",
        {"apiKey": ODDS_API_KEY}
    )
    if not events:
        return None
    return events[0]

def get_event_odds(event_id: str):
    return odds_get(
        f"/sports/soccer_spain_la_liga/events/{event_id}/odds",
        {
            "apiKey": ODDS_API_KEY,
            "regions": "us,us2",
            "markets": "player_shots,player_shots_on_target,player_to_receive_card",
            "oddsFormat": "decimal"
        }
    )

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
        found_any = False

        for book in bookmakers[:2]:
            mensaje += f"🏪 {book.get('title', 'Bookmaker')}\n"

            for market in book.get("markets", []):
                market_name = market.get("key")
                if market_name in ["player_shots", "player_shots_on_target", "player_to_receive_card"]:
                    outcomes = market.get("outcomes", [])
                    if outcomes:
                        found_any = True
                    for outcome in outcomes[:3]:
                        jugador = outcome.get("description") or outcome.get("name") or "Jugador"
                        linea = outcome.get("point", "")
                        cuota = outcome.get("price", "")
                        mensaje += f"{jugador} | {market_name} {linea} → {cuota}\n"
            mensaje += "\n"

        if not found_any:
            return f"No encontré mercados de jugador para {home} vs {away}"

        return mensaje

    except Exception as e:
        return f"Error cuotas ❌ {e}"

def get_first_player_from_props():
    event = get_first_laliga_event()
    if not event:
        return None

    odds_data = get_event_odds(event["id"])

    for book in odds_data.get("bookmakers", []):
        for market in book.get("markets", []):
            if market.get("key") == "player_shots_on_target":
                outcomes = market.get("outcomes", [])
                if outcomes:
                    return outcomes[0].get("description")
    return None

def test_probability_from_odds(price: float) -> float:
    implied = 1 / price
    boosted = implied + 0.10
    return min(boosted, 0.85)

def team_names_match(a: str, b: str) -> bool:
    na = normalize_text(a)
    nb = normalize_text(b)
    return na == nb or na in nb or nb in na

def get_matching_fixture_for_event(event):
    try:
        event_date = (event.get("commence_time") or "")[:10]
        home = event.get("home_team", "")
        away = event.get("away_team", "")

        data = football_get("/fixtures", {
            "league": LEAGUE_ID,
            "season": SEASON,
            "date": event_date
        })

        fixtures = data.get("response", [])
        for f in fixtures:
            home_name = f.get("teams", {}).get("home", {}).get("name", "")
            away_name = f.get("teams", {}).get("away", {}).get("name", "")

            if team_names_match(home, home_name) and team_names_match(away, away_name):
                return f

        # fallback suave
        for f in fixtures:
            home_name = f.get("teams", {}).get("home", {}).get("name", "")
            away_name = f.get("teams", {}).get("away", {}).get("name", "")
            if team_names_match(home, home_name) or team_names_match(away, away_name):
                return f

        return None
    except Exception:
        return None

def get_team_squad(team_id: int):
    try:
        data = football_get("/players/squads", {"team": team_id})
        response = data.get("response", [])
        if not response:
            return []
        players = response[0].get("players", [])
        return players
    except Exception:
        return []

def candidate_queries(name: str):
    norm = normalize_text(name)
    parts = norm.split()
    queries = [norm]

    if len(parts) >= 2:
        queries.append(" ".join(parts[:2]))
        queries.append(" ".join(parts[-2:]))
        queries.append(parts[0])
        queries.append(parts[-1])
    elif len(parts) == 1:
        queries.append(parts[0])

    out = []
    seen = set()
    for q in queries:
        if q and q not in seen:
            out.append(q)
            seen.add(q)
    return out

def search_players_api(query: str):
    try:
        data = football_get("/players", {"search": query})
        return data.get("response", [])
    except Exception:
        return []

def resolve_player_id_from_event_player(name: str, event) -> int | None:
    norm_target = normalize_text(name)
    target_parts = norm_target.split()

    fixture = get_matching_fixture_for_event(event)
    if fixture:
        home_team_id = fixture.get("teams", {}).get("home", {}).get("id")
        away_team_id = fixture.get("teams", {}).get("away", {}).get("id")

        squad = []
        if home_team_id:
            squad.extend(get_team_squad(home_team_id))
        if away_team_id:
            squad.extend(get_team_squad(away_team_id))

        best_id = None
        best_score = -1

        for p in squad:
            candidate_name = normalize_text(p.get("name", ""))
            score = 0

            if candidate_name == norm_target:
                score = 100
            elif norm_target in candidate_name:
                score = 90
            elif candidate_name in norm_target:
                score = 80
            else:
                shared = sum(1 for part in target_parts if part in candidate_name.split())
                score = shared * 20

            if score > best_score:
                best_score = score
                best_id = p.get("id")

        if best_id and best_score >= 20:
            return best_id

    # fallback a búsqueda global
    best_match = None
    best_score = -1

    for query in candidate_queries(name):
        results = search_players_api(query)

        for item in results:
            player = item.get("player", {})
            candidate_name = normalize_text(player.get("name", ""))

            score = 0
            if candidate_name == norm_target:
                score = 100
            elif norm_target in candidate_name:
                score = 90
            elif candidate_name in norm_target:
                score = 80
            else:
                shared = sum(1 for part in target_parts if part in candidate_name.split())
                score = shared * 20

            if score > best_score:
                best_score = score
                best_match = player

    if best_match and best_score >= 20:
        return best_match.get("id")

    return None

def get_player_stats(player_name):
    event = get_first_laliga_event()
    if not event:
        return "No encontré evento para resolver el jugador"

    player_id = resolve_player_id_from_event_player(player_name, event)
    if not player_id:
        return f"No encontré ID para {player_name}"

    try:
        data = football_get("/players", {
            "id": player_id,
            "season": SEASON
        })

        if not data.get("response"):
            return f"No encontré estadísticas para {player_name}"

        # elegimos la estadística con más apariciones
        stats_blocks = data["response"][0].get("statistics", [])
        if not stats_blocks:
            return f"No encontré estadísticas para {player_name}"

        best_block = max(
            stats_blocks,
            key=lambda s: (s.get("games", {}).get("appearences") or 0)
        )

        tiros = best_block.get("shots", {}).get("total") or 0
        tiros_puerta = best_block.get("shots", {}).get("on") or 0
        partidos = best_block.get("games", {}).get("appearences") or 1
        team_name = best_block.get("team", {}).get("name", "Equipo")

        media_tiros = round(tiros / partidos, 2) if partidos else 0
        media_tiros_puerta = round(tiros_puerta / partidos, 2) if partidos else 0

        return (
            f"📊 Stats {player_name}\n\n"
            f"Equipo: {team_name}\n"
            f"Partidos: {partidos}\n"
            f"Tiros totales: {tiros}\n"
            f"Tiros a puerta: {tiros_puerta}\n"
            f"Media tiros: {media_tiros}\n"
            f"Media tiros a puerta: {media_tiros_puerta}"
        )

    except Exception as e:
        return f"Error stats ❌ {e}"

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
                            f"Bank: 1000€\n\n"
                            f"⚠️ Este cálculo aún es de prueba. El siguiente paso será usar estadísticas reales."
                        )

        if checked == 0:
            return "No encontré props de tiros a puerta para analizar."
        return "He revisado props, pero no encontré value con el filtro actual."

    except Exception as e:
        return f"Error value ❌ {e}"

def stats_command():
    try:
        jugador = get_first_player_from_props()
        if not jugador:
            return "No encontré jugador"

        return get_player_stats(jugador)

    except Exception as e:
        return f"Error stats ❌ {e}"

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
                        events = odds_get(
                            "/sports/soccer_spain_la_liga/events",
                            {"apiKey": ODDS_API_KEY}
                        )

                        if not events:
                            send_message("No hay partidos disponibles")
                            continue

                        mensaje = "📊 Próximos partidos:\n\n"
                        for partido in events[:5]:
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
