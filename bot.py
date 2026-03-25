import os
import time
import json
import math
import threading
import urllib.request
import urllib.parse
from datetime import datetime, timezone

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
ODDS_API_KEY = os.getenv("ODDS_API_KEY", "").strip()

SPORT_KEY = "basketball_nba"
REGIONS = "us"
ODDS_FORMAT = "decimal"

MARKETS = {
    "player_points": {
        "label": "Puntos",
        "stat_key": "PTS",
        "emoji": "🏀",
        "aliases": ["puntos", "pts", "points"],
    },
    "player_rebounds": {
        "label": "Rebotes",
        "stat_key": "REB",
        "emoji": "💥",
        "aliases": ["rebotes", "reb", "rebounds"],
    },
    "player_assists": {
        "label": "Asistencias",
        "stat_key": "AST",
        "emoji": "🎯",
        "aliases": ["asistencias", "ast", "assists"],
    },
    "player_threes": {
        "label": "Triples",
        "stat_key": "FG3M",
        "emoji": "3️⃣",
        "aliases": ["triples", "threes", "fg3m"],
    },
}

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

MIN_EDGE = 0.05
MIN_PRICE = 1.62
MAX_PRICE = 2.55
MIN_AVG_MINUTES = 20.0
MIN_GAMES_FOR_MODEL = 6
MAX_RESULTS = 5
MAX_EVENTS_TO_SCAN = 4
CACHE_TTL_SECONDS = 1800
NBA_REQUEST_SLEEP = 0.8

HIGH_VARIANCE_PENALTY = 0.03
CONSISTENCY_BONUS = 0.03
CONSISTENCY_PENALTY = 0.04
TREND_BONUS = 0.04
TREND_PENALTY = 0.04
OPP_BONUS = 0.03
OPP_PENALTY = 0.03

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
GAMELOG_CACHE = {}

def send_message(chat_id: int, text: str) -> None:
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = urllib.parse.urlencode({
        "chat_id": str(chat_id),
        "text": text[:4000],
    }).encode("utf-8")

    req = urllib.request.Request(url, data=payload, method="POST")
    with urllib.request.urlopen(req, timeout=30) as response:
        response.read()

def http_get_json(url: str, headers=None, timeout=30):
    req = urllib.request.Request(url, headers=headers or {}, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))

def get_updates(offset=None):
    params = {"timeout": 25}
    if offset is not None:
        params["offset"] = offset

    url = f"https://api.telegram.org/bot{TOKEN}/getUpdates?" + urllib.parse.urlencode(params)

    with urllib.request.urlopen(url, timeout=35) as response:
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

def safe_float(value):
    try:
        return float(value)
    except Exception:
        return 0.0

def clamp(x, low, high):
    return max(low, min(high, x))

def decimal_implied_prob(price: float) -> float:
    if not price or price <= 1:
        return 0.0
    return 1.0 / price

def normal_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))

def normalize_name(name: str) -> str:
    return " ".join((name or "").lower().replace(".", "").replace("’", "'").split())

def american_season_string():
    now = datetime.now(timezone.utc)
    year = now.year
    month = now.month
    start_year = year if month >= 9 else year - 1
    end_year_short = str((start_year + 1) % 100).zfill(2)
    return f"{start_year}-{end_year_short}"

def average(values):
    return sum(values) / len(values) if values else 0.0

def weighted_mean(values, weights):
    if not values or not weights or len(values) != len(weights):
        return 0.0
    total_w = sum(weights)
    if total_w <= 0:
        return 0.0
    return sum(v * w for v, w in zip(values, weights)) / total_w

def sample_std(values):
    if len(values) < 2:
        return 0.0
    m = average(values)
    variance = sum((x - m) ** 2 for x in values) / (len(values) - 1)
    return math.sqrt(variance)

def hit_rate(values, line, over=True):
    if not values:
        return 0.0
    if over:
        return sum(1 for v in values if v > line) / len(values)
    return sum(1 for v in values if v < line) / len(values)

def trend_score(avg5, avg10):
    if avg10 <= 0:
        return 0.0
    return (avg5 - avg10) / max(avg10, 1.0)

def coefficient_variation(values):
    if not values:
        return 999.0
    m = average(values)
    if m == 0:
        return 999.0
    return sample_std(values) / m

def get_team_abbr(full_team_name: str) -> str:
    return TEAM_NAME_TO_ABBR.get(full_team_name, "")

def parse_market_filter(text: str):
    t = normalize_name(text)
    for market_key, meta in MARKETS.items():
        for alias in meta["aliases"]:
            if alias in t:
                return market_key
    return None

def format_optional(value, decimals=2):
    if value is None:
        return "n/d"
    return f"{value:.{decimals}f}"

def clean_command(text: str) -> str:
    text = text.strip()
    if not text.startswith("/"):
        return text

    parts = text.split(" ", 1)
    cmd = parts[0]
    rest = parts[1] if len(parts) > 1 else ""

    if "@" in cmd:
        cmd = cmd.split("@", 1)[0]

    return f"{cmd} {rest}".strip()

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
        raise RuntimeError("Sin datos en commonallplayers")

    rowset = result_sets[0]["rowSet"]
    headers = result_sets[0]["headers"]
    idx = {name: i for i, name in enumerate(headers)}

    players = []
    for row in rowset:
        players.append({
            "player_id": row[idx["PERSON_ID"]],
            "display_name": row[idx["DISPLAY_FIRST_LAST"]],
            "team_abbr": row[idx.get("TEAM_ABBREVIATION", -1)] if "TEAM_ABBREVIATION" in idx else "",
        })

    cache_set(PLAYER_CACHE, "all_players", players)
    return players

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
        raise RuntimeError("Sin datos en playergamelog")

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

    return games

def build_player_model(games, stat_key, line, bet_type, opponent_abbr=None):
    if not games or len(games) < MIN_GAMES_FOR_MODEL:
        return None

    last_10 = games[:10]
    last_5 = games[:5]
    if len(last_5) < 3:
        return None

    vals10 = [g[stat_key] for g in last_10]
    vals5 = [g[stat_key] for g in last_5]
    mins10 = [g["MIN"] for g in last_10]
    mins5 = [g["MIN"] for g in last_5]

    avg10 = average(vals10)
    avg5 = average(vals5)
    avg_min10 = average(mins10)
    avg_min5 = average(mins5)

    if avg_min10 < MIN_AVG_MINUTES:
        return None

    stdev10 = sample_std(vals10)
    if stdev10 < 1.25:
        stdev10 = 1.25

    cv10 = coefficient_variation(vals10)

    is_over = bet_type == "Over"
    hit5 = hit_rate(vals5, line, over=is_over)
    hit10 = hit_rate(vals10, line, over=is_over)

    trend = trend_score(avg5, avg10)

    opp_avg = None
    if opponent_abbr:
        opp_games = [g for g in games[:15] if opponent_abbr in (g["MATCHUP"] or "")]
        if len(opp_games) >= 2:
            opp_avg = average([g[stat_key] for g in opp_games])

    base_projection = weighted_mean(
        [avg5, avg10, opp_avg if opp_avg is not None else avg10],
        [0.50, 0.35, 0.15]
    )

    minute_factor = 1.0
    if avg_min5 >= 36:
        minute_factor += 0.05
    elif avg_min5 >= 33:
        minute_factor += 0.03
    elif avg_min5 < 24:
        minute_factor -= 0.08
    elif avg_min5 < 28:
        minute_factor -= 0.04

    projection = base_projection * minute_factor

    if trend >= 0.12:
        projection += TREND_BONUS * max(avg10, 1.0)
    elif trend <= -0.12:
        projection -= TREND_PENALTY * max(avg10, 1.0)

    if opp_avg is not None:
        if opp_avg >= avg10 * 1.12:
            projection += OPP_BONUS * max(avg10, 1.0)
        elif opp_avg <= avg10 * 0.88:
            projection -= OPP_PENALTY * max(avg10, 1.0)

    if cv10 > 0.75:
        projection -= HIGH_VARIANCE_PENALTY * max(avg10, 1.0)

    if is_over:
        z = ((line + 0.5) - projection) / stdev10
        est_prob = 1.0 - normal_cdf(z)
    else:
        z = ((line - 0.5) - projection) / stdev10
        est_prob = normal_cdf(z)

    consistency = weighted_mean([hit5, hit10], [0.60, 0.40])

    if consistency >= 0.70:
        est_prob += CONSISTENCY_BONUS
    elif consistency <= 0.35:
        est_prob -= CONSISTENCY_PENALTY

    est_prob = clamp(est_prob, 0.05, 0.92)

    return {
        "avg5": avg5,
        "avg10": avg10,
        "avg_min5": avg_min5,
        "avg_min10": avg_min10,
        "opp_avg": opp_avg,
        "projection": projection,
        "hit5": hit5,
        "hit10": hit10,
        "estimated_prob": est_prob,
    }

def grade_pick(edge, estimated_prob, hit5, hit10):
    score = 0
    if edge >= 0.15:
        score += 3
    elif edge >= 0.10:
        score += 2
    elif edge >= 0.06:
        score += 1

    if estimated_prob >= 0.62:
        score += 2
    elif estimated_prob >= 0.57:
        score += 1

    if hit5 >= 0.80:
        score += 2
    elif hit5 >= 0.60:
        score += 1

    if hit10 >= 0.70:
        score += 1

    if score >= 7:
        return "A+"
    if score >= 5:
        return "A"
    if score >= 4:
        return "B+"
    if score >= 3:
        return "B"
    return "C"

def analyze_event_props(event, market_filter=None):
    event_id = event["id"]
    home = event.get("home_team", "")
    away = event.get("away_team", "")
    home_abbr = get_team_abbr(home)
    away_abbr = get_team_abbr(away)

    market_keys = [market_filter] if market_filter else list(MARKETS.keys())
    props_data = get_event_props(event_id, market_keys)
    bookmakers = props_data.get("bookmakers", [])

    candidates = []
    for book in bookmakers:
        book_name = book.get("title", "Bookmaker")

        for market in book.get("markets", []):
            market_key = market.get("key")
            if market_key not in MARKETS:
                continue

            stat_key = MARKETS[market_key]["stat_key"]
            meta = MARKETS[market_key]

            for outcome in market.get("outcomes", []):
                bet_type = outcome.get("name")
                line = outcome.get("point")
                price = outcome.get("price")
                player_name = outcome.get("description", "")

                if bet_type not in ("Over", "Under"):
                    continue
                if line is None or not isinstance(price, (int, float)):
                    continue
                if not player_name:
                    continue
                if price < MIN_PRICE or price > MAX_PRICE:
                    continue

                guessed_team = home_abbr
                opponent_abbr = away_abbr

                player = find_player_by_name_and_team(player_name, home_abbr)
                if player is None:
                    player = find_player_by_name_and_team(player_name, away_abbr)
                    guessed_team = away_abbr
                    opponent_abbr = home_abbr

                if player is None:
                    continue

                try:
                    games = get_player_game_log(player["player_id"])
                except Exception as e:
                    print("player log error:", player_name, e)
                    continue

                model = build_player_model(games, stat_key, float(line), bet_type, opponent_abbr)
                if not model:
                    continue

                implied = decimal_implied_prob(float(price))
                estimated = model["estimated_prob"]
                edge = estimated * float(price) - 1.0

                if edge < MIN_EDGE:
                    continue

                candidates.append({
                    "event": f"{away} vs {home}",
                    "book": book_name,
                    "market_label": meta["label"],
                    "emoji": meta["emoji"],
                    "player_name": player["display_name"],
                    "team_abbr": guessed_team,
                    "bet_type": bet_type,
                    "line": float(line),
                    "price": float(price),
                    "implied": implied,
                    "estimated": estimated,
                    "edge": edge,
                    "avg5": model["avg5"],
                    "avg10": model["avg10"],
                    "avg_min5": model["avg_min5"],
                    "avg_min10": model["avg_min10"],
                    "opp_avg": model["opp_avg"],
                    "projection": model["projection"],
                    "hit5": model["hit5"],
                    "hit10": model["hit10"],
                    "grade": grade_pick(edge, estimated, model["hit5"], model["hit10"]),
                })

    candidates.sort(key=lambda x: (x["edge"], x["estimated"], x["hit5"], x["avg_min5"]), reverse=True)
    return candidates

def get_best_nba_value_message(market_filter=None):
    events = get_nba_events()
    if not events:
        return "No encontré partidos NBA ahora mismo."

    all_candidates = []
    for event in events[:MAX_EVENTS_TO_SCAN]:
        try:
            all_candidates.extend(analyze_event_props(event, market_filter))
        except Exception as e:
            print("event error:", e)

    if not all_candidates:
        return "No encontré value ahora mismo."

    best = sorted(
        all_candidates,
        key=lambda x: (x["edge"], x["estimated"], x["hit5"], x["avg_min5"]),
        reverse=True
    )[0]

    return (
        f"🔥 VALUE NBA DETECTADO\n\n"
        f"Partido: {best['event']}\n"
        f"Casa: {best['book']}\n\n"
        f"{best['emoji']} Jugador: {best['player_name']} ({best['team_abbr']})\n"
        f"Mercado: {best['market_label']}\n"
        f"Apuesta: {best['bet_type']} {best['line']}\n"
        f"Cuota: {best['price']:.2f}\n"
        f"Nota: {best['grade']}\n\n"
        f"Media L5: {best['avg5']:.2f}\n"
        f"Media L10: {best['avg10']:.2f}\n"
        f"Vs rival: {format_optional(best['opp_avg'])}\n"
        f"Min L5: {best['avg_min5']:.1f}\n"
        f"Min L10: {best['avg_min10']:.1f}\n"
        f"Proyección: {best['projection']:.2f}\n"
        f"Hit L5: {best['hit5']:.0%}\n"
        f"Hit L10: {best['hit10']:.0%}\n\n"
        f"Prob. implícita: {best['implied']:.1%}\n"
        f"Prob. estimada: {best['estimated']:.1%}\n"
        f"Edge: {best['edge']:.1%}"
    )

def get_top_nba_values_message(market_filter=None):
    events = get_nba_events()
    if not events:
        return "No encontré partidos NBA."

    all_candidates = []
    for event in events[:MAX_EVENTS_TO_SCAN]:
        try:
            all_candidates.extend(analyze_event_props(event, market_filter))
        except Exception as e:
            print("event error:", e)

    if not all_candidates:
        return "No encontré picks ahora mismo."

    top = sorted(
        all_candidates,
        key=lambda x: (x["edge"], x["estimated"], x["hit5"], x["avg_min5"]),
        reverse=True
    )[:MAX_RESULTS]

    msg = "📈 TOP VALUES NBA\n\n"
    for i, pick in enumerate(top, start=1):
        msg += (
            f"{i}. {pick['player_name']} ({pick['team_abbr']})\n"
            f"{pick['market_label']} | {pick['bet_type']} {pick['line']} @ {pick['price']:.2f}\n"
            f"Partido: {pick['event']}\n"
            f"Casa: {pick['book']}\n"
            f"Grade: {pick['grade']} | Edge: {pick['edge']:.1%} | Prob: {pick['estimated']:.1%}\n"
            f"L5: {pick['avg5']:.2f} | L10: {pick['avg10']:.2f} | Hit5: {pick['hit5']:.0%}\n\n"
        )
    return msg[:4000]

def get_nba_props_board_message():
    events = get_nba_events()
    if not events:
        return "No encontré partidos NBA."

    event = events[0]
    props_data = get_event_props(event["id"], list(MARKETS.keys()))
    bookmakers = props_data.get("bookmakers", [])

    if not bookmakers:
        return "No hay props disponibles ahora mismo."

    home = event.get("home_team", "Local")
    away = event.get("away_team", "Visitante")
    msg = f"📋 Props NBA\n\n{away} vs {home}\n\n"

    shown = 0
    for book in bookmakers[:2]:
        msg += f"🏪 {book.get('title', 'Bookmaker')}\n"
        count_book = 0

        for market in book.get("markets", []):
            mk = market.get("key")
            if mk not in MARKETS:
                continue

            market_label = MARKETS[mk]["label"]
            for outcome in market.get("outcomes", []):
                desc = outcome.get("description", "")
                name = outcome.get("name", "")
                point = outcome.get("point")
                price = outcome.get("price")

                if not desc or name not in ("Over", "Under") or point is None:
                    continue

                msg += f"{market_label} | {desc} | {name} {point} @ {price}\n"
                shown += 1
                count_book += 1

                if count_book >= 10:
                    break

            if count_book >= 10:
                break

        msg += "\n"

    return msg[:4000] if shown else "No encontré props útiles."

def get_nba_player_message(player_name: str):
    if not player_name.strip():
        return "Uso: /nba_player Nombre Apellido"

    player = find_player_by_name_and_team(player_name)
    if player is None:
        return f"No encontré al jugador: {player_name}"

    games = get_player_game_log(player["player_id"])
    if not games:
        return f"No hay game log para {player['display_name']}"

    last_5 = games[:5]
    avg_min = average([g["MIN"] for g in last_5])
    avg_pts = average([g["PTS"] for g in last_5])
    avg_reb = average([g["REB"] for g in last_5])
    avg_ast = average([g["AST"] for g in last_5])
    avg_3pm = average([g["FG3M"] for g in last_5])

    lines = "\n".join(
        f"{g['GAME_DATE']} | {g['MATCHUP']} | MIN {g['MIN']:.0f} | PTS {g['PTS']:.0f} | REB {g['REB']:.0f} | AST {g['AST']:.0f} | 3PM {g['FG3M']:.0f}"
        for g in last_5
    )

    return (
        f"👤 {player['display_name']} ({player.get('team_abbr', '')})\n\n"
        f"Media L5:\n"
        f"MIN {avg_min:.1f} | PTS {avg_pts:.1f} | REB {avg_reb:.1f} | AST {avg_ast:.1f} | 3PM {avg_3pm:.1f}\n\n"
        f"Últimos partidos:\n{lines}"
    )

def handle_command(text: str):
    t = clean_command(text)

    if t == "/start":
        return (
            "🤖 Bot NBA listo.\n\n"
            "Comandos:\n"
            "/ping\n"
            "/nba_props\n"
            "/nba_value\n"
            "/nba_value puntos\n"
            "/nba_value rebotes\n"
            "/nba_value asistencias\n"
            "/nba_value triples\n"
            "/nba_top\n"
            "/nba_top puntos\n"
            "/nba_top rebotes\n"
            "/nba_top asistencias\n"
            "/nba_top triples\n"
            "/nba_player Nombre Apellido"
        )

    if t == "/ping":
        return "pong 🟢"

    if t == "/nba_props":
        return get_nba_props_board_message()

    if t.startswith("/nba_value"):
        rest = t.replace("/nba_value", "", 1).strip()
        market_filter = parse_market_filter(rest) if rest else None
        return get_best_nba_value_message(market_filter)

    if t.startswith("/nba_top"):
        rest = t.replace("/nba_top", "", 1).strip()
        market_filter = parse_market_filter(rest) if rest else None
        return get_top_nba_values_message(market_filter)

    if t.startswith("/nba_player"):
        player_name = t.replace("/nba_player", "", 1).strip()
        return get_nba_player_message(player_name)

    return "Comando no reconocido."

def command_loop():
    offset = None
    while True:
        try:
            data = get_updates(offset)
            if not data.get("ok"):
                print("Telegram getUpdates error:", data)
                time.sleep(5)
                continue

            for item in data.get("result", []):
                update_id = item["update_id"]
                offset = update_id + 1

                message = item.get("message", {})
                text = (message.get("text", "") or "").strip()
                chat = message.get("chat", {})
                chat_id = chat.get("id")

                if not text or not chat_id:
                    continue

                print(f"Mensaje recibido: {text} | chat_id={chat_id}")

                try:
                    response = handle_command(text)
                except Exception as e:
                    print("handle_command error:", e)
                    response = f"Error interno ❌ {e}"

                try:
                    send_message(chat_id, response)
                except Exception as e:
                    print("send_message error:", e)

        except Exception as e:
            print("loop error:", e)
            time.sleep(5)

def main():
    if not TOKEN or not ODDS_API_KEY:
        raise RuntimeError("Faltan variables: TELEGRAM_BOT_TOKEN y/o ODDS_API_KEY")

    print("Bot arrancando...")
    command_loop()

if __name__ == "__main__":
    main()
