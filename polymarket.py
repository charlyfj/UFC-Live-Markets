import json
import re
import time
from collections import defaultdict
from datetime import date, datetime, timezone

import requests

try:
    from .config import GAMMA_URL, CARD_ORDER, ODDS_API_KEY
    from .state import S
    from .utils import fmt_vol
except ImportError:
    from config import GAMMA_URL, CARD_ORDER, ODDS_API_KEY
    from state import S
    from utils import fmt_vol


# ── event classification ──────────────────────────────────────────────────────

MANUAL_TARGET_DATE = "2026-04-25"


def _manual_target_date():
    if not MANUAL_TARGET_DATE:
        return None
    if isinstance(MANUAL_TARGET_DATE, date):
        return MANUAL_TARGET_DATE
    return date.fromisoformat(str(MANUAL_TARGET_DATE))


def _game_start_date(event):
    for market in event.get("markets", []):
        gst = market.get("gameStartTime")
        if not gst:
            continue
        try:
            return datetime.fromisoformat(str(gst).replace(" ", "T")).date()
        except Exception:
            pass
    return None


def _is_fighter_matchup(event):
    title = event.get("title", "")
    if "vs." not in title and " vs " not in title:
        return False
    markets = event.get("markets", [])
    if not markets:
        return False
    prop = {"yes", "no", "over", "under"}
    for market in markets:
        raw = market.get("outcomes", "[]")
        outcomes = json.loads(raw) if isinstance(raw, str) else raw
        if not outcomes:
            continue
        normalized = [str(outcome).strip().lower() for outcome in outcomes[:2]]
        if len(normalized) >= 2 and all(outcome not in prop for outcome in normalized):
            return True
    return False


def card_type(event):
    m = re.search(r'\(([^,)]+),\s*([^)]+)\)', event.get("title", ""))
    return m.group(2).strip() if m else "Other"


def _market_sort_key(mkt):
    q  = mkt["question"].lower()
    la = mkt["label_a"].lower()
    lb = mkt["label_b"].lower()
    prop = {"yes", "no", "over", "under"}
    if la not in prop and lb not in prop: return 0   # moneyline
    if any(k in q for k in ["ko", "tko", "submission", "decision", "distance", "method", "finish"]): return 1
    if "round" in q or "o/u" in q: return 2
    return 3


# ── data fetching ─────────────────────────────────────────────────────────────

def fetch_all_matchups():
    """Paginate through all active UFC fighter-matchup events."""
    all_events = []
    limit, offset = 100, 0
    while True:
        r = requests.get(GAMMA_URL, params={
            "tag_slug": "ufc", "active": "true", "closed": "false",
            "limit": limit, "offset": offset,
        })
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break
        all_events.extend(batch)
        if len(batch) < limit:
            break
        offset += limit
    return [e for e in all_events if _is_fighter_matchup(e)]


def fetch_fights(target_date=None):
    """Return (fights, date). If target_date is None, picks the nearest upcoming card."""
    matchups = fetch_all_matchups()

    if target_date is None:
        target_date = _manual_target_date()

    if target_date is not None:
        fights = [e for e in matchups if _game_start_date(e) == target_date]
        fights.sort(key=lambda e: (CARD_ORDER.get(card_type(e), 3), e.get("title", "")))
        return fights, target_date

    by_date = defaultdict(list)
    for e in matchups:
        d = _game_start_date(e)
        if d:
            by_date[d].append(e)
    if not by_date:
        return [], None
    nearest = min(by_date)
    fights = by_date[nearest]
    fights.sort(key=lambda e: (CARD_ORDER.get(card_type(e), 3), e.get("title", "")))
    return fights, nearest


def fetch_fight_by_slug(slug):
    r = requests.get(GAMMA_URL, params={"slug": slug})
    r.raise_for_status()
    data = r.json()
    return data[0] if data else None


# ── state bootstrap ───────────────────────────────────────────────────────────

def load_state(target_date=None):
    raw_fights, actual_date = fetch_fights(target_date)
    S.saturday = actual_date
    fights_out, idx = [], 0

    for fi, fight in enumerate(raw_fights):
        title = fight.get("title", "").strip()
        card  = card_type(fight)
        mkts  = []

        for m in fight.get("markets", []):
            raw_tok  = m.get("clobTokenIds", "[]")
            tokens   = json.loads(raw_tok) if isinstance(raw_tok, str) else raw_tok
            if len(tokens) < 2:
                continue

            raw_out  = m.get("outcomes", "[]")
            outcomes = json.loads(raw_out) if isinstance(raw_out, str) else raw_out
            raw_px   = m.get("outcomePrices", "[]")
            prices   = json.loads(raw_px) if isinstance(raw_px, str) else raw_px

            label_a = outcomes[0] if outcomes else "A"
            label_b = outcomes[1] if len(outcomes) > 1 else "B"
            price_a = float(prices[0]) if prices else None
            price_b = float(prices[1]) if len(prices) > 1 else None

            S.prices[tokens[0]]       = {"price": price_a, "bid": None, "ask": None}
            S.prices[tokens[1]]       = {"price": price_b, "bid": None, "ask": None}
            S.token_to_idx[tokens[0]] = idx
            S.token_to_idx[tokens[1]] = idx
            S.token_to_slot[tokens[0]] = "a"
            S.token_to_slot[tokens[1]] = "b"

            mkt_dict = {
                "idx": idx, "question": m.get("question", ""),
                "label_a": label_a, "label_b": label_b,
                "token_a": tokens[0], "token_b": tokens[1],
                "vol_24h": fmt_vol(m.get("volume24hr")),
            }
            mkt_dict["kind"] = "moneyline" if _market_sort_key(mkt_dict) == 0 else "prop"
            mkts.append(mkt_dict)
            idx += 1

        mkts.sort(key=_market_sort_key)
        fights_out.append({"fi": fi, "title": title, "card": card, "markets": mkts})

    S.fights = fights_out
    return list(S.token_to_idx.keys())


# ── snapshot serialiser ───────────────────────────────────────────────────────

def snapshot():
    now = time.monotonic()
    fights_data = []

    for fight in S.fights:
        mkts = []
        ml_px_a = ml_px_b = None

        for m in fight["markets"]:
            i    = m["idx"]
            px_a = S.prices.get(m["token_a"], {})
            px_b = S.prices.get(m["token_b"], {})
            lt   = S.trades.get(i, {})
            upd  = S.updates.get(i)
            age  = round(now - upd, 1) if upd else None

            if m["kind"] == "moneyline":
                ml_px_a = px_a.get("price")
                ml_px_b = px_b.get("price")

            mkts.append({
                "idx": i, "question": m["question"],
                "label_a": m["label_a"], "label_b": m["label_b"], "kind": m["kind"],
                "price_a": px_a.get("price"), "price_b": px_b.get("price"),
                "bid_a": px_a.get("bid"), "ask_a": px_a.get("ask"),
                "last_price": lt.get("price"), "last_label": lt.get("label"),
                "vol_24h": m["vol_24h"], "age": age,
            })

        bod = S.book_odds.get(fight["title"])
        book_snap = None
        if bod:
            gap_a = (ml_px_a - bod["consensus_a"]) if ml_px_a is not None else None
            gap_b = (ml_px_b - bod["consensus_b"]) if ml_px_b is not None else None
            book_snap = {**bod, "gap_a": gap_a, "gap_b": gap_b}

        fights_data.append({
            "fi": fight["fi"], "title": fight["title"], "card": fight["card"],
            "markets": mkts, "book_odds": book_snap,
        })

    odds_age = round(time.time() - S.odds_fetched) if S.odds_fetched else None
    return json.dumps({
        "saturday":     S.saturday.strftime("%A, %B %d %Y") if S.saturday else "",
        "time":         datetime.now(timezone.utc).strftime("%H:%M:%S UTC"),
        "connected":    S.ws_connected,
        "msg_count":    S.msg_count,
        "has_odds_key": bool(ODDS_API_KEY),
        "odds_age":     odds_age,
        "fights":       fights_data,
    })
