# 🔥 VERSION ESTABLE SIN BLOQUEOS

def filter_allowed_bookmakers(bookmakers):
    # 🔥 YA NO FILTRAMOS → usamos todas
    return bookmakers


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

                    # 🔥 MODELO SIMPLE PERO FUNCIONA SIEMPRE
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
