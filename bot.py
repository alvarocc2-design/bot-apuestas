import os
import time
import json
import math
import threading
import urllib.request
import urllib.parse
from datetime import datetime, timezone

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
ODDS_API_KEY = os.getenv("ODDS_API_KEY", "").strip()

SPORT_KEY = "basketball_nba"
REGIONS = "us"
ODDS_FORMAT = "decimal"

# Mercados a analizar
MARKETS = {
    "player_points": {
        "label": "Puntos",
        "stat_key": "PTS",
        "emoji": "🏀",
    },
    "player_rebounds": {
        "label": "Rebotes",
        "stat_key": "REB",
        "emoji": "💥",
    },
    "player_assists": {
        "label": "Asistencias",
        "stat_key": "AST",
        "emoji": "🎯",
    },
    "player_threes": {
        "label": "Triples",
        "stat_key": "FG3M",
        "emoji": "3️⃣",
    },
}

# Configuración del modelo
MIN_EDGE = 0.05
MIN_PRICE = 1.65
MAX_PRICE = 2.40
MIN_AVG_MINUTES = 20
MAX_RESULTS = 5
CACHE_TTL_SECONDS = 1800
NBA_REQUEST_SLEEP = 0.8

# Cabeceras para stats.nba.com
NBA_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.nba.com/",
    "Origin": "https://www.nba.com",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    "Connection": "keep-alive",
}

PLAYER_CACHE = {}
TEAM_CACHE = {}
GAMELOG_CACHE = {}

TEAM_NAME_TO_ABBR = {
    "Atlanta Hawks": "ATL",
    "Boston Celtics": "BOS",
    "Brooklyn Nets": "BKN",
    "Charlotte Hornets": "CHA",
    "Chicago Bulls": "CHI",
    "Cleveland Cavaliers": "CLE",
    "Dallas Mavericks": "DAL",
    "Denver Nuggets": "DEN",
    "Detroit Pistons": "DET",
    "Golden State Warriors": "GSW",
    "Houston Rockets": "HOU",
    "Indiana Pacers": "IND",
    "LA Clippers": "LAC",
    "Los Angeles Clippers": "LAC",
    "Los Angeles Lakers": "LAL",
    "Memphis Grizzlies": "MEM",
    "Miami Heat": "MIA",
    "Milwaukee Bucks": "MIL",
    "Minnesota Timberwolves": "MIN",
    "New Orleans Pelicans": "NOP",
    "New York Knicks": "NYK",
    "Oklahoma City Thunder": "OKC",
    "Orlando Magic": "ORL",
    "Philadelphia 76ers": "PHI",
    "Phoenix Suns": "PHX",
    "Portland Trail Blazers": "POR",
    "Sacramento Kings": "SAC",
    "San Antonio Spurs": "SAS",
    "Toronto Raptors": "TOR",
    "Utah Jazz": "UTA",
    "Washington Wizards": "WAS",
}

def send_message(text: str) -> None:
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = urllib.parse.urlencode({
        "chat_id": CHAT_ID,
        "text": text[:4000],  # Telegram limit de mensaje
    }).encode("utf-8")

    req = urllib.request.Request(url, data=payload, method="POST")
    with urllib.request.urlopen(req, timeout=30) as response:
        response.read()

def http_get_json(url: str, headers=None, timeout=30):
    req = urllib.request.Request(url, headers=headers or {}, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))

def get_updates(offset=None):
    url = f"https://api.telegram.org/bot{TOKEN}/getUpdates"
    if offset is not None:
        url += "?" + urllib.parse.urlencode({"offset": offset})

    with urllib.request.urlopen(url, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))

def now_ts():
    return time.time()

def cache_get(cache: dict, key: str):
    item = cache.get(key)
    if not item:
        return None
    if now_ts() - item["ts"] > CACHE_TTL_SECONDS:
        cache.pop(key, None)
        return None
    return item["data"]

def cache_set(cache: dict, key: str, data):
    cache[key] = {"ts": now_ts(), "data": data}

def decimal_implied_prob(price: float) -> float:
    if not price or price <= 1:
        return 0.0
    return 1.0 / price

def clamp(x, low, high):
    return max(low, min(high, x))

def normal_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))

def american_season_string():
    # temporada tipo 2025-26
    now = datetime.now(timezone.utc)
    year = now.year
    month = now.month
    start_year = year if month >= 9 else year - 1
    end_year_short = str((start_year + 1) % 100).zfill(2)
    return f"{start_year}-{end_year_short}"

def get_nba_events():
    url = f"https://api.the-odds-api.com/v4/sports/{SPORT_KEY}/odds"
    url += "?" + urllib.parse.urlencode({
        "apiKey": ODDS_API_KEY,
        "regions": REGIONS,
        "markets": "h2h",
        "oddsFormat": ODDS_FORMAT,
    })
    return http_get_json(url)

def get_event_props(event_id: str, market_keys):
    url = f"https://api.the-odds-api.com/v4/sports/{SPORT_KEY}/events/{event_id}/odds"
    url += "?" + urllib.parse.urlencode({
        "apiKey": ODDS_API_KEY,
        "regions": REGIONS,
        "markets": ",".join(market_keys),
        "oddsFormat": ODDS_FORMAT,
    })
    return http_get_json(url)

def get_all_players():
    cached = cache_get(PLAYER_CACHE, "all_players")
    if cached is not None:
        return cached

    season = american_season_string()
    url = "https://stats.nba.com/stats/commonallplayers"
    url += "?" + urllib.parse.urlencode({
        "IsOnlyCurrentSeason": "1",
        "LeagueID": "00",
        "Season": season,
    })

    data = http_get_json(url, headers=NBA_HEADERS, timeout=30)
    time.sleep(NBA_REQUEST_SLEEP)

    result_sets = data.get("resultSets", [])
    if not result_sets:
        raise RuntimeError("NBA commonallplayers sin datos")

    rowset = result_sets[0]["rowSet"]
    headers = result_sets[0]["headers"]
    idx = {name: i for i, name in enumerate(headers)}

    players = []
    for row in rowset:
        players.append({
            "player_id": row[idx["PERSON_ID"]],
            "display_name": row[idx["DISPLAY_FIRST_LAST"]],
            "team_id": row[idx["TEAM_ID"]],
            "team_city": row[idx.get("TEAM_CITY", -1)] if "TEAM_CITY" in idx else "",
            "team_name": row[idx.get("TEAM_NAME", -1)] if "TEAM_NAME" in idx else "",
            "team_abbr": row[idx.get("TEAM_ABBREVIATION", -1)] if "TEAM_ABBREVIATION" in idx else "",
        })

    cache_set(PLAYER_CACHE, "all_players", players)
    return players

def normalize_name(name: str) -> str:
    return " ".join((name or "").lower().replace(".", "").replace("’", "'").split())

def find_player_by_name_and_team(player_name: str, team_abbr: str = ""):
    players = get_all_players()
    target = normalize_name(player_name)

    exact = []
    partial = []

    for p in players:
        p_name = normalize_name(p["display_name"])
        if p_name == target:
            if not team_abbr or p.get("team_abbr") == team_abbr:
                exact.append(p)
        elif target in p_name or p_name in target:
            if not team_abbr or p.get("team_abbr") == team_abbr:
                partial.append(p)

    if exact:
        return exact[0]
    if partial:
        return partial[0]
    return None

def get_player_game_log(player_id: int):
    cache_key = f"gamelog_{player_id}"
    cached = cache_get(GAMELOG_CACHE, cache_key)
    if cached is not None:
        return cached

    season = american_season_string()
    url = "https://stats.nba.com/stats/playergamelog"
    url += "?" + urllib.parse.urlencode({
        "DateFrom": "",
        "DateTo": "",
        "LeagueID": "00",
        "PlayerID": str(player_id),
        "Season": season,
        "SeasonType": "Regular Season",
    })

    data = http_get_json(url, headers=NBA_HEADERS, timeout=30)
    time.sleep(NBA_REQUEST_SLEEP)

    result_sets = data.get("resultSets", [])
    if not result_sets:
        raise RuntimeError("NBA playergamelog sin datos")

    rowset = result_sets[0]["rowSet"]
    headers = result_sets[0]["headers"]
    idx = {name: i for i, name in enumerate(headers)}

    games = []
    for row in rowset:
        games.append({
            "GAME_DATE": row[idx["GAME_DATE"]],
            "MATCHUP": row[idx["MATCHUP"]],
            "MIN": safe_float(row[idx["MIN"]]),
            "PTS": safe_float(row[idx["PTS"]]),
            "REB": safe_float(row[idx["REB"]]),
            "AST": safe_float(row[idx["AST"]]),
            "FG3M": safe_float(row[idx["FG3M"]]),
        })

    cache_set(GAMELOG_CACHE, cache_key, games)
    return games

def safe_float(value):
    try:
        return float(value)
    except Exception:
        return 0.0

def get_team_abbr(full_team_name: str) -> str:
    return TEAM_NAME_TO_ABBR.get(full_team_name, "")

def weighted_mean(values, weights):
    if not values or not weights or len(values) != len(weights):
        return 0.0
    s_w = sum(weights)
    if s_w <= 0:
        return 0.0
    return sum(v * w for v, w in zip(values, weights)) / s_w

def sample_std(values):
    if len(values) < 2:
        return 0.0
    m = sum(values) / len(values)
    variance = sum((x - m) ** 2 for x in values) / (len(values) - 1)
    return math.sqrt(variance)

def compute_prop_model(games, stat_key, opponent_abbr=None):
    if not games:
        return None

    last_10 = games[:10]
    last_5 = games[:5]
    if len(last_10) < 4:
        return None

    vals_10 = [g[stat_key] for g in last_10]
    mins_10 = [g["MIN"] for g in last_10]
    avg10 = sum(vals_10) / len(vals_10)
    avg5 = sum(g[stat_key] for g in last_5) / len(last_5) if last_5 else avg10
    avg_min = sum(mins_10) / len(mins_10)

    opp_games = []
    if opponent_abbr:
        opp_games = [g for g in games[:15] if opponent_abbr in (g["MATCHUP"] or "")]
    opp_avg = None
    if len(opp_games) >= 2:
        opp_avg = sum(g[stat_key] for g in opp_games) / len(opp_games)

    base = weighted_mean(
        [avg5, avg10, opp_avg if opp_avg is not None else avg10],
        [0.45, 0.40, 0.15]
    )

    # Ajuste por minutos
    minute_factor = 1.0
    if avg_min >= 36:
        minute_factor += 0.04
    elif avg_min >= 32:
        minute_factor += 0.02
    elif avg_min < 24:
        minute_factor -= 0.07
    elif avg_min < 28:
        minute_factor -= 0.03

    projection = base * minute_factor
    stdev = sample_std(vals_10)
    if stdev < 1.5:
        stdev = 1.5

    hit_rate_10 = sum(1 for v in vals_10 if v > 0) / len(vals_10)

    return {
        "avg5": avg5,
        "avg10": avg10,
        "opp_avg": opp_avg,
        "avg_min": avg_min,
        "projection": projection,
        "stdev": stdev,
        "hit_rate_10": hit_rate_10,
        "games_used": len(last_10),
    }

def probability_over(line: float, projection: float, stdev: float) -> float:
    # Aproximación continua con corrección de medio punto
    z = ((line + 0.5) - projection) / stdev
    return 1.0 - normal_cdf(z)

def probability_under(line: float, projection: float, stdev: float) -> float:
    return 1.0 - probability_over(line, projection, stdev)

def stake_from_edge(edge: float) -> int:
    if edge >= 0.18:
        return 30
    if edge >= 0.12:
        return 20
    if edge >= 0.08:
        return 15
    return 10

def extract_best_props_for_event(event):
    event_id = event["id"]
    home = event.get("home_team", "")
    away = event.get("away_team", "")
    home_abbr = get_team_abbr(home)
    away_abbr = get_team_abbr(away)

    props_data = get_event_props(event_id, list(MARKETS.keys()))
    bookmakers = props_data.get("bookmakers", [])
    if not bookmakers:
        return []

    candidates = []

    for book in bookmakers:
        book_name = book.get("title", "Bookmaker")

        for market in book.get("markets", []):
            market_key = market.get("key")
            if market_key not in MARKETS:
                continue

            market_meta = MARKETS[market_key]
            stat_key = market_meta["stat_key"]

            for outcome in market.get("outcomes", []):
                name = outcome.get("name")          # Over / Under
                line = outcome.get("point")
                price = outcome.get("price")
                desc = outcome.get("description", "")  # suele traer nombre del jugador

                if name not in ("Over", "Under"):
                    continue
                if not desc or line is None or not isinstance(price, (int, float)):
                    continue
                if price < MIN_PRICE or price > MAX_PRICE:
                    continue

                guessed_team = home_abbr
                opponent = away_abbr

                # Intento simple de resolver por nombre y equipo
                player = find_player_by_name_and_team(desc, home_abbr)
                if player is None:
                    player = find_player_by_name_and_team(desc, away_abbr)
                    guessed_team = away_abbr
                    opponent = home_abbr

                if player is None:
                    continue

                try:
                    games = get_player_game_log(player["player_id"])
                except Exception:
                    continue

                model = compute_prop_model(games, stat_key, opponent_abbr=opponent)
                if not model:
                    continue
                if model["avg_min"] < MIN_AVG_MINUTES:
                    continue

                if name == "Over":
                    est_prob = probability_over(float(line), model["projection"], model["stdev"])
                else:
                    est_prob = probability_under(float(line), model["projection"], model["stdev"])

                implied = decimal_implied_prob(float(price))
                edge = est_prob * float(price) - 1.0

                if edge < MIN_EDGE:
                    continue

                candidates.append({
                    "event": f"{away} vs {home}",
                    "book": book_name,
                    "market_key": market_key,
                    "market_label": market_meta["label"],
                    "emoji": market_meta["emoji"],
                    "player_name": player["display_name"],
                    "team_abbr": guessed_team,
                    "opponent_abbr": opponent,
                    "bet_type": name,
                    "line": float(line),
                    "price": float(price),
                    "implied": implied,
                    "estimated": est_prob,
                    "edge": edge,
                    "avg5": model["avg5"],
                    "avg10": model["avg10"],
                    "opp_avg": model["opp_avg"],
                    "avg_min": model["avg_min"],
                    "projection": model["projection"],
                    "stdev": model["stdev"],
                })

    candidates.sort(key=lambda x: (x["edge"], x["estimated"], x["avg_min"]), reverse=True)
    return candidates[:MAX_RESULTS]

def get_best_nba_value_message():
    try:
        events = get_nba_events()
        if not events:
            return "No encontré partidos NBA ahora mismo."

        all_candidates = []

        for event in events[:4]:  # limita peticiones
            try:
                picks = extract_best_props_for_event(event)
                all_candidates.extend(picks)
            except Exception as e:
                print("event error:", e)
                continue

        if not all_candidates:
            return "No encontré value ahora mismo en NBA."

        all_candidates.sort(key=lambda x: (x["edge"], x["estimated"], x["avg_min"]), reverse=True)
        best = all_candidates[0]
        stake = stake_from_edge(best["edge"])

        opp_avg_text = (
            f"{best['opp_avg']:.2f}" if best["opp_avg"] is not None else "n/d"
        )

        return (
            f"🔥 VALUE NBA DETECTADO\n\n"
            f"Partido: {best['event']}\n"
            f"Casa: {best['book']}\n\n"
            f"{best['emoji']} Jugador: {best['player_name']} ({best['team_abbr']})\n"
            f"Mercado: {best['market_label']}\n"
            f"Apuesta: {best['bet_type']} {best['line']}\n"
            f"Cuota: {best['price']:.2f}\n\n"
            f"Media L5: {best['avg5']:.2f}\n"
            f"Media L10: {best['avg10']:.2f}\n"
            f"Vs rival: {opp_avg_text}\n"
            f"Minutos medios: {best['avg_min']:.1f}\n"
            f"Proyección: {best['projection']:.2f}\n\n"
            f"Prob. implícita: {best['implied']:.1%}\n"
            f"Prob. estimada: {best['estimated']:.1%}\n"
            f"Edge: {best['edge']:.1%}\n"
            f"Stake sugerido: {stake}€\n\n"
            f"⚠️ Modelo simple: usa líneas de The Odds API + game log oficial NBA"
        )
    except Exception as e:
        return f"Error NBA value ❌ {e}"

def get_nba_props_board_message():
    try:
        events = get_nba_events()
        if not events:
            return "No encontré partidos NBA."

        event = events[0]
        home = event.get("home_team", "Local")
        away = event.get("away_team", "Visitante")

        props_data = get_event_props(event["id"], list(MARKETS.keys()))
        bookmakers = props_data.get("bookmakers", [])
        if not bookmakers:
            return "No hay props disponibles ahora mismo."

        msg = f"📋 Props NBA\n\n{away} vs {home}\n\n"
        shown = 0

        for book in bookmakers[:2]:
            msg += f"🏪 {book.get('title', 'Bookmaker')}\n"
            per_book = 0

            for market in book.get("markets", []):
                mk = market.get("key")
                if mk not in MARKETS:
                    continue

                market_label = MARKETS[mk]["label"]
                for outcome in market.get("outcomes", [])[:8]:
                    desc = outcome.get("description", "")
                    name = outcome.get("name", "")
                    point = outcome.get("point")
                    price = outcome.get("price")

                    if not desc or name not in ("Over", "Under") or point is None:
                        continue

                    msg += f"{market_label} | {desc} | {name} {point} @ {price}\n"
                    per_book += 1
                    shown += 1

                    if per_book >= 10:
                        break

                if per_book >= 10:
                    break

            msg += "\n"

        if shown == 0:
            return "No encontré props útiles."

        return msg[:4000]
    except Exception as e:
        return f"Error props ❌ {e}"

def get_nba_player_message(player_name: str):
    try:
        if not player_name.strip():
            return "Uso: /nba_player Nombre Apellido"

        player = find_player_by_name_and_team(player_name)
        if player is None:
            return f"No encontré al jugador: {player_name}"

        games = get_player_game_log(player["player_id"])
        if not games:
            return f"No hay game log para {player['display_name']}"

        last_5 = games[:5]
        avg_min = sum(g["MIN"] for g in last_5) / len(last_5)
        avg_pts = sum(g["PTS"] for g in last_5) / len(last_5)
        avg_reb = sum(g["REB"] for g in last_5) / len(last_5)
        avg_ast = sum(g["AST"] for g in last_5) / len(last_5)
        avg_3pm = sum(g["FG3M"] for g in last_5) / len(last_5)

        lines = "\n".join(
            f"{g['GAME_DATE']} | {g['MATCHUP']} | MIN {g['MIN']:.0f} | "
            f"PTS {g['PTS']:.0f} | REB {g['REB']:.0f} | AST {g['AST']:.0f} | 3PM {g['FG3M']:.0f}"
            for g in last_5
        )

        return (
            f"👤 {player['display_name']} ({player.get('team_abbr', '')})\n\n"
            f"Media últimos 5:\n"
            f"MIN {avg_min:.1f} | PTS {avg_pts:.1f} | REB {avg_reb:.1f} | "
            f"AST {avg_ast:.1f} | 3PM {avg_3pm:.1f}\n\n"
            f"Últimos partidos:\n{lines}"
        )
    except Exception as e:
        return f"Error jugador ❌ {e}"

def heartbeat():
    while True:
        try:
            time.sleep(600)
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
                text = (message.get("text", "") or "").strip()

                if text == "/start":
                    send_message(
                        "🤖 Bot NBA listo.\n\n"
                        "Comandos:\n"
                        "/ping\n"
                        "/nba_props\n"
                        "/nba_value\n"
                        "/nba_player Nombre Apellido"
                    )

                elif text == "/ping":
                    send_message("pong 🟢")

                elif text == "/nba_props":
                    send_message(get_nba_props_board_message())

                elif text == "/nba_value":
                    send_message(get_best_nba_value_message())

                elif text.startswith("/nba_player"):
                    player_name = text.replace("/nba_player", "", 1).strip()
                    send_message(get_nba_player_message(player_name))

        except Exception as e:
            print("loop error:", e)
            time.sleep(5)

def main():
    if not TOKEN or not CHAT_ID or not ODDS_API_KEY:
        raise RuntimeError("Faltan variables: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, ODDS_API_KEY")

    send_message("🔥 Bot NBA Props iniciado 🔥")

    t1 = threading.Thread(target=heartbeat, daemon=True)
    t2 = threading.Thread(target=command_loop, daemon=True)

    t1.start()
    t2.start()

    while True:
        time.sleep(60)

if __name__ == "__main__":
    main()
