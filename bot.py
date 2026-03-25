import os
import time
import threading
import json
import urllib.request
import urllib.parse
import unicodedata
from datetime import datetime, timedelta, timezone

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
ODDS_API_KEY = os.getenv("ODDS_API_KEY", "").strip()
API_FOOTBALL_KEY = os.getenv("API_FOOTBALL_KEY", "").strip()

BANKROLL = 1000
MIN_EDGE = 0.08

CURRENT_YEAR = datetime.now(timezone.utc).year
SEASONS_TO_TRY = [CURRENT_YEAR, CURRENT_YEAR - 1]

LEAGUES = {
    "laliga": {
        "name": "LaLiga EA Sports",
        "odds_sport_key": "soccer_spain_la_liga",
        "football_league_id": 140,
    },
    "hypermotion": {
        "name": "LaLiga Hypermotion",
        "odds_sport_key": "soccer_spain_segunda_division",
        "football_league_id": 141,
    },
    "premier": {
        "name": "Premier League",
        "odds_sport_key": "soccer_epl",
        "football_league_id": 39,
    },
    "serie_a": {
        "name": "Serie A",
        "odds_sport_key": "soccer_italy_serie_a",
        "football_league_id": 135,
    },
    "bundesliga": {
        "name": "Bundesliga",
        "odds_sport_key": "soccer_germany_bundesliga",
        "football_league_id": 78,
    },
    "ligue_1": {
        "name": "Ligue 1",
        "odds_sport_key": "soccer_france_ligue_one",
        "football_league_id": 61,
    },
}

ACTIVE_LEAGUE = "hypermotion"


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


def current_league_config():
    return LEAGUES[ACTIVE_LEAGUE]


def current_sport_key():
    return current_league_config()["odds_sport_key"]


def current_football_league_id():
    return current_league_config()["football_league_id"]


def current_league_name():
    return current_league_config()["name"]


def list_leagues_message():
    lines = [f"🏆 Liga activa: {ACTIVE_LEAGUE} ({current_league_name()})", "", "Ligas disponibles:"]
    for key, cfg in LEAGUES.items():
        marker = "✅" if key == ACTIVE_LEAGUE else "•"
        lines.append(f"{marker} {key} → {cfg['name']}")
    lines.append("")
    lines.append("Usa: /setliga <clave>")
    return "\n".join(lines)


def set_active_league(key: str):
    global ACTIVE_LEAGUE
    key = (key or "").strip().lower()
    if key not in LEAGUES:
        return False, f"Liga no válida: {key}"
    ACTIVE_LEAGUE = key
    return True, f"✅ Liga cambiada a {key} ({current_league_name()})"


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


def get_first_event():
    events = odds_get(
        f"/sports/{current_sport_key()}/events",
        {"apiKey": ODDS_API_KEY}
    )
    if not events:
        return None
    return events[0]


def get_all_events(limit=5):
    events = odds_get(
        f"/sports/{current_sport_key()}/events",
        {"apiKey": ODDS_API_KEY}
    )
    return events[:limit] if events else []


def get_event_odds(event_id: str):
    return odds_get(
        f"/sports/{current_sport_key()}/events/{event_id}/odds",
        {
            "apiKey": ODDS_API_KEY,
            "regions": "us,us2",
            "markets": "alternate_totals_corners,alternate_spreads_corners",
            "oddsFormat": "decimal"
        }
    )


def team_names_match(a: str, b: str) -> bool:
    na = normalize_text(a)
    nb = normalize_text(b)
    return na == nb or na in nb or nb in na


def get_dates_to_try(event):
    raw = event.get("commence_time")
    dates = []

    if raw:
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            dates.append(dt.date())
            dates.append((dt - timedelta(days=1)).date())
            dates.append((dt + timedelta(days=1)).date())
        except Exception:
            pass

    today = datetime.now(timezone.utc).date()
    for d in [today - timedelta(days=1), today, today + timedelta(days=1)]:
        if d not in dates:
            dates.append(d)

    return [d.isoformat() for d in dates]


def get_matching_fixture_for_event(event):
    try:
        home = event.get("home_team", "")
        away = event.get("away_team", "")

        for season in SEASONS_TO_TRY:
            for date_str in get_dates_to_try(event):
                data = football_get("/fixtures", {
                    "league": current_football_league_id(),
                    "season": season,
                    "date": date_str
                })

                fixtures = data.get("response", [])

                for f in fixtures:
                    home_name = f.get("teams", {}).get("home", {}).get("name", "")
                    away_name = f.get("teams", {}).get("away", {}).get("name", "")
                    if team_names_match(home, home_name) and team_names_match(away, away_name):
                        return f

                for f in fixtures:
                    home_name = f.get("teams", {}).get("home", {}).get("name", "")
                    away_name = f.get("teams", {}).get("away", {}).get("name", "")
                    if team_names_match(home, home_name) or team_names_match(away, away_name):
                        return f

        return None

    except Exception as e:
        print("get_matching_fixture_for_event error:", e)
        return None


def extract_corner_kicks_from_statistics(stats_response, team_name):
    """
    stats_response viene de /fixtures/statistics?fixture=ID
    """
    norm_team = normalize_text(team_name)

    for team_block in stats_response.get("response", []):
        block_team_name = team_block.get("team", {}).get("name", "")
        if not team_names_match(norm_team, block_team_name):
            continue

        for stat in team_block.get("statistics", []):
            stat_type = stat.get("type", "")
            stat_value = stat.get("value", 0)

            if normalize_text(stat_type) in ["corner kicks", "corners", "corner kicks "]:
                try:
                    return int(stat_value or 0)
                except Exception:
                    return 0
    return None


def get_fixture_statistics(fixture_id: int):
    return football_get("/fixtures/statistics", {"fixture": fixture_id})


def get_recent_team_fixtures(team_id: int, limit: int = 5):
    data = football_get("/fixtures", {
        "team": team_id,
        "league": current_football_league_id(),
        "last": limit
    })
    return data.get("response", [])


def get_team_corner_series(team_id: int, team_name: str, limit: int = 5):
    fixtures = get_recent_team_fixtures(team_id, limit=limit)
    values = []

    for fx in fixtures:
        fixture_id = fx.get("fixture", {}).get("id")
        if not fixture_id:
            continue

        try:
            stats = get_fixture_statistics(fixture_id)
            corners = extract_corner_kicks_from_statistics(stats, team_name)
            if corners is not None:
                values.append(corners)
        except Exception:
            continue

    return values


def get_fixture_team_ids(event):
    fixture = get_matching_fixture_for_event(event)
    if not fixture:
        return None

    home = fixture.get("teams", {}).get("home", {})
    away = fixture.get("teams", {}).get("away", {})

    return {
        "home_id": home.get("id"),
        "away_id": away.get("id"),
        "home_name": home.get("name", event.get("home_team", "Local")),
        "away_name": away.get("name", event.get("away_team", "Visitante")),
        "fixture_id": fixture.get("fixture", {}).get("id")
    }


def get_corners_partidos_message():
    try:
        events = get_all_events(limit=5)
        if not events:
            return f"No hay partidos disponibles en {current_league_name()}"

        mensaje = f"📊 Próximos partidos ({current_league_name()}):\n\n"
        for partido in events:
            home = partido.get("home_team", "Local")
            away = partido.get("away_team", "Visitante")
            mensaje += f"{home} vs {away}\n"

        return mensaje
    except Exception as e:
        return f"Error corners_partidos ❌ {e}"


def get_corners_odds_message():
    try:
        event = get_first_event()
        if not event:
            return "No encontré eventos."

        event_id = event.get("id")
        home = event.get("home_team", "Local")
        away = event.get("away_team", "Visitante")

        odds_data = get_event_odds(event_id)
        bookmakers = odds_data.get("bookmakers", [])

        if not bookmakers:
            return f"No encontré cuotas de córners para {home} vs {away}"

        mensaje = f"🚩 Cuotas de córners:\n{home} vs {away}\nLiga: {current_league_name()}\n\n"
        found_any = False

        for book in bookmakers[:2]:
            mensaje += f"🏪 {book.get('title', 'Bookmaker')}\n"

            for market in book.get("markets", []):
                market_name = market.get("key")
                if market_name in ["alternate_totals_corners", "alternate_spreads_corners"]:
                    outcomes = market.get("outcomes", [])
                    if outcomes:
                        found_any = True

                    for outcome in outcomes[:6]:
                        name = outcome.get("name", "")
                        point = outcome.get("point", "")
                        price = outcome.get("price", "")
                        desc = outcome.get("description", "")

                        extra = f" ({desc})" if desc else ""
                        mensaje += f"{market_name} | {name} {point}{extra} → {price}\n"

            mensaje += "\n"

        if not found_any:
            return f"No encontré mercados de córners para {home} vs {away}"

        return mensaje

    except Exception as e:
        return f"Error corners_cuotas ❌ {e}"


def get_corners_stats_message():
    try:
        event = get_first_event()
        if not event:
            return "No encontré evento"

        ids = get_fixture_team_ids(event)
        if not ids:
            return "No encontré fixture para ese partido"

        home_series = get_team_corner_series(ids["home_id"], ids["home_name"], limit=5) if ids["home_id"] else []
        away_series = get_team_corner_series(ids["away_id"], ids["away_name"], limit=5) if ids["away_id"] else []

        home_avg = round(sum(home_series) / len(home_series), 2) if home_series else 0
        away_avg = round(sum(away_series) / len(away_series), 2) if away_series else 0
        total_avg = round(home_avg + away_avg, 2)

        return (
            f"📊 Stats córners ({current_league_name()})\n\n"
            f"{ids['home_name']}: {home_series if home_series else 'sin datos'}\n"
            f"Media: {home_avg}\n\n"
            f"{ids['away_name']}: {away_series if away_series else 'sin datos'}\n"
            f"Media: {away_avg}\n\n"
            f"Media total estimada: {total_avg}"
        )

    except Exception as e:
        return f"Error corners_stats ❌ {e}"


def get_corners_value_message():
    try:
        event = get_first_event()
        if not event:
            return "No encontré eventos para analizar."

        ids = get_fixture_team_ids(event)
        if not ids:
            return "No encontré fixture para ese partido"

        home_series = get_team_corner_series(ids["home_id"], ids["home_name"], limit=5) if ids["home_id"] else []
        away_series = get_team_corner_series(ids["away_id"], ids["away_name"], limit=5) if ids["away_id"] else []

        if not home_series or not away_series:
            return "No hay suficientes stats de córners para analizar."

        total_estimated = round(
            (sum(home_series) / len(home_series)) + (sum(away_series) / len(away_series)),
            2
        )

        odds_data = get_event_odds(event.get("id"))
        bookmakers = odds_data.get("bookmakers", [])

        if not bookmakers:
            return f"No encontré cuotas de córners para {event.get('home_team')} vs {event.get('away_team')}"

        checked = 0

        for book in bookmakers:
            book_name = book.get("title", "Bookmaker")

            for market in book.get("markets", []):
                if market.get("key") != "alternate_totals_corners":
                    continue

                for outcome in market.get("outcomes", []):
                    name = outcome.get("name", "")
                    point = outcome.get("point")
                    price = outcome.get("price")

                    if not isinstance(price, (int, float)) or point is None:
                        continue

                    checked += 1

                    try:
                        line = float(point)
                    except Exception:
                        continue

                    # modelo simple inicial: comparar media total estimada contra la línea
                    if name.lower() == "over":
                        if total_estimated <= line:
                            continue

                        margin = total_estimated - line
                        implied_prob = 1 / price
                        model_prob = min(0.50 + (margin * 0.08), 0.85)
                        edge = (model_prob * price) - 1

                        if edge >= MIN_EDGE:
                            stake = pick_stake(edge)

                            return (
                                f"🚩 VALUE CÓRNERS DETECTADO\n\n"
                                f"Liga: {current_league_name()}\n"
                                f"Partido: {event.get('home_team')} vs {event.get('away_team')}\n"
                                f"Casa: {book_name}\n\n"
                                f"Mercado: Over córners totales\n"
                                f"Línea: {line}\n"
                                f"Cuota: {price}\n\n"
                                f"Media estimada local: {round(sum(home_series)/len(home_series),2)}\n"
                                f"Media estimada visitante: {round(sum(away_series)/len(away_series),2)}\n"
                                f"Media total estimada: {total_estimated}\n\n"
                                f"Prob. implícita: {implied_prob:.1%}\n"
                                f"Prob. estimada: {model_prob:.1%}\n"
                                f"Edge: {edge:.1%}\n\n"
                                f"Stake sugerido: {stake}€\n"
                                f"Bank: {BANKROLL}€\n\n"
                                f"⚠️ Modelo inicial de córners. Se puede afinar después."
                            )

        if checked == 0:
            return "No encontré líneas de córners totales para analizar."
        return "He revisado córners, pero no encontré value con el filtro actual."

    except Exception as e:
        return f"Error corners_value ❌ {e}"


def get_debug_fixture_message():
    try:
        event = get_first_event()
        if not event:
            return "No encontré evento"

        home = event.get("home_team", "")
        away = event.get("away_team", "")
        mensaje = f"🔎 DEBUG FIXTURE\n\nLiga activa: {ACTIVE_LEAGUE} ({current_league_name()})\n\nOdds API:\n{home} vs {away}\n\n"

        found_any = False

        for season in SEASONS_TO_TRY:
            for date_str in get_dates_to_try(event):
                data = football_get("/fixtures", {
                    "league": current_football_league_id(),
                    "season": season,
                    "date": date_str
                })

                fixtures = data.get("response", [])
                if fixtures:
                    found_any = True
                    mensaje += f"Temporada {season} | Fecha {date_str}\n"
                    for f in fixtures[:5]:
                        h = f.get("teams", {}).get("home", {}).get("name", "")
                        a = f.get("teams", {}).get("away", {}).get("name", "")
                        mensaje += f"- {h} vs {a}\n"
                    mensaje += "\n"

        if not found_any:
            return mensaje + "No encontré fixtures en esas fechas/temporadas"

        return mensaje

    except Exception as e:
        return f"Error debug_fixture ❌ {e}"


def heartbeat():
    while True:
        try:
            time.sleep(300)
            send_message("Sigo activo ✅")
        except Exception as e:
            print("heartbeat error:", e)
            time.sleep(30)


def command_loop():
    global ACTIVE_LEAGUE

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
                text = (message.get("text", "") or "").strip()

                if text == "/start":
                    send_message(
                        "🤖 Bot córners conectado.\n"
                        "Comandos:\n"
                        "/ligas\n"
                        "/setliga <clave>\n"
                        "/ping\n"
                        "/status\n"
                        "/test_odds\n"
                        "/test_football\n"
                        "/corners_partidos\n"
                        "/corners_cuotas\n"
                        "/corners_stats\n"
                        "/corners_value\n"
                        "/debug_fixture"
                    )
                elif text == "/ping":
                    send_message("pong 🟢")
                elif text == "/status":
                    send_message(f"Estado actual: bot estable, Telegram OK.\nLiga activa: {ACTIVE_LEAGUE} ({current_league_name()})")
                elif text == "/ligas":
                    send_message(list_leagues_message())
                elif text.startswith("/setliga"):
                    parts = text.split(maxsplit=1)
                    if len(parts) < 2:
                        send_message("Uso: /setliga <clave>")
                    else:
                        ok, msg = set_active_league(parts[1])
                        send_message(msg)
                elif text == "/test_odds":
                    send_message(test_odds_api())
                elif text == "/test_football":
                    send_message(test_football_api())
                elif text == "/corners_partidos":
                    send_message(get_corners_partidos_message())
                elif text == "/corners_cuotas":
                    send_message(get_corners_odds_message())
                elif text == "/corners_stats":
                    send_message(get_corners_stats_message())
                elif text == "/corners_value":
                    send_message(get_corners_value_message())
                elif text == "/debug_fixture":
                    send_message(get_debug_fixture_message())

        except Exception as e:
            print("command_loop error:", e)
            time.sleep(5)


def main():
    send_message(f"🔥 Bot córners iniciando 🔥\nLiga activa: {ACTIVE_LEAGUE} ({current_league_name()})")
    t1 = threading.Thread(target=heartbeat, daemon=True)
    t2 = threading.Thread(target=command_loop, daemon=True)
    t1.start()
    t2.start()

    while True:
        time.sleep(60)


if __name__ == "__main__":
    main()
