import re
import time
import threading

import requests

from config import ODDS_API_URL, ODDS_API_KEY, ODDS_REFRESH, BOOK_PRIORITY
from state import S
from utils import implied


def _fighter_names(title):
    """'UFC FN: A vs. B (Div, Card)' → ('A', 'B')"""
    m = re.search(r':\s*(.+?)\s*\(', title)
    if not m:
        return None, None
    vs = m.group(1)
    parts = re.split(r'\s+vs\.?\s+', vs, maxsplit=1, flags=re.IGNORECASE)
    return (parts[0].strip(), parts[1].strip()) if len(parts) == 2 else (None, None)


def _name_match(a, b):
    """True if two name strings share at least one meaningful word."""
    stop = {"jr", "sr", "ii", "iii", "de", "da", "dos", "van"}
    wa = set(a.lower().split()) - stop
    wb = set(b.lower().split()) - stop
    return bool(wa & wb)


def fetch_book_odds():
    if not ODDS_API_KEY:
        return
    try:
        r = requests.get(ODDS_API_URL, params={
            "apiKey": ODDS_API_KEY, "regions": "us",
            "markets": "h2h", "oddsFormat": "american",
        }, timeout=12)
        r.raise_for_status()
        events = r.json()
    except Exception as e:
        print(f"[odds] API error: {e}")
        return

    new_odds = {}
    for fight in S.fights:
        fa, fb = _fighter_names(fight["title"])
        if not fa:
            continue

        for ev in events:
            home, away = ev.get("home_team", ""), ev.get("away_team", "")
            a_home = _name_match(fa, home) or _name_match(fa, away)
            b_home = _name_match(fb, home) or _name_match(fb, away)
            if not (a_home and b_home):
                continue

            name_a = home if _name_match(fa, home) else away
            name_b = away if name_a == home else home

            bookmakers = sorted(
                ev.get("bookmakers", []),
                key=lambda b: BOOK_PRIORITY.index(b["key"]) if b["key"] in BOOK_PRIORITY else 99,
            )

            books = []
            for bkm in bookmakers[:5]:
                h2h = next((m for m in bkm.get("markets", []) if m["key"] == "h2h"), None)
                if not h2h:
                    continue
                out = {o["name"]: o["price"] for o in h2h.get("outcomes", [])}
                oa, ob = out.get(name_a), out.get(name_b)
                if oa is None or ob is None:
                    continue
                books.append({
                    "name":   bkm["title"],
                    "odds_a": oa,  "odds_b": ob,
                    "impl_a": implied(oa), "impl_b": implied(ob),
                })

            if not books:
                continue

            cons_a = sum(b["impl_a"] for b in books) / len(books)
            cons_b = sum(b["impl_b"] for b in books) / len(books)
            vig    = cons_a + cons_b - 1

            new_odds[fight["title"]] = {
                "label_a": fa, "label_b": fb,
                "consensus_a": cons_a, "consensus_b": cons_b,
                "vig": vig, "books": books,
            }
            break

    S.book_odds    = new_odds
    S.odds_fetched = time.time()
    print(f"[odds] refreshed — {len(new_odds)}/{len(S.fights)} fights matched")


def start_odds_thread():
    def _run():
        while True:
            fetch_book_odds()
            time.sleep(ODDS_REFRESH)
    threading.Thread(target=_run, daemon=True).start()
