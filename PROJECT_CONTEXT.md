# UFC Polymarket Live — Project Context & Handoff

> **Purpose of this file:** bring a new Claude Code session up to speed instantly.
> Last updated: 2026-04-25 (rev 2).

---

## What This Project Is

A real-time Flask web app that displays live UFC fight odds from **Polymarket** (via WebSocket) and **sportsbook consensus lines** (via The Odds API), plus an **AI Predictions tab** where you can paste JSON from ChatGPT, Gemini, and Grok and compare their fight predictions side-by-side.

---

## File Map

```
d:\Poly\ufc\
├── ufc_fight_detail.py          # CLI tool: fetches & prints all fights for the next UFC date
├── ufc_fights.py                # Older/simpler UFC fetch utility
├── polymarket_ufc.py            # Earlier standalone Polymarket scraper
│
└── live_data\
    ├── .env                     # API keys (ODDS_API_KEY=ae2e3ec4...)
    ├── ufc_fight_detail_ws.py   # Early WebSocket prototype (no Flask UI)
    ├── ufc_fight_detail_ws_app.py      # v1 Flask app — Polymarket only, no book odds
    └── ufc_fight_detail_ws_app_v2.py  # ✅ MAIN FILE — see full breakdown below
    └── export_exe\              # PyInstaller build artifacts (not active)
```

**The only file being actively developed is `ufc_fight_detail_ws_app_v2.py`.**

---

## Running the App

```bash
# Dev (reads .env automatically)
cd d:\Poly\ufc\live_data
python ufc_fight_detail_ws_app_v2.py

# Override to a specific date
python ufc_fight_detail_ws_app_v2.py --date 2026-05-03

# Custom port
python ufc_fight_detail_ws_app_v2.py --port 8080

# Open in browser
http://localhost:5000
```

**Dependencies:**
```bash
pip install flask requests websockets
```

**API key** is in `.env` alongside the script — loaded automatically at startup, no `set` command needed:
```
ODDS_API_KEY=ae2e3ec407a8c6f8fa02f7009461a029
```

---

## Architecture of `ufc_fight_detail_ws_app_v2.py`

### Python backend (lines 1–450 approx)

| Section | What it does |
|---|---|
| `_load_dotenv()` | Loads `.env` from same dir; also handles compiled `.exe` mode via `_baked_env` module |
| `_State` class (`S`) | Single global state object: fights list, live prices dict, book odds dict, WS connection status |
| `_fetch_all_matchups()` | **Paginates** Gamma API (100 at a time) to get ALL active UFC fighter-matchup events |
| `_fetch_fights(target_date=None)` | Returns `(fights, date)`. If `target_date` is `None`, groups events by date and picks the **nearest upcoming card** — same logic as `ufc_fight_detail.py` |
| `_game_start_date(event)` | Checks **all markets** for `gameStartTime` (not just `markets[0]`) — fixes fights that were silently dropped |
| `load_state(saturday)` | Builds `S.fights` and token lookup tables from REST response; called once at startup |
| `fetch_book_odds()` | Calls The Odds API every 5 min; fuzzy-matches fighter names to Polymarket titles; computes consensus implied prob + vig |
| `snapshot()` | Serializes full state to JSON for SSE stream; computes live Poly-vs-Book gap each tick |
| `_apply(msg)` | Handles WS messages: `book` (bid/ask), `price_change`, `last_trade_price` |
| `_ws_loop()` | Async WebSocket loop with heartbeat, auto-reconnect |
| Flask routes | `GET /` → HTML page; `GET /stream` → SSE stream at 0.5s interval |

### HTML/CSS/JS frontend (large string `HTML`, lines ~450–end)

**Two tabs:**

#### Tab 1 — Live Markets
- Sticky header: card date, server time, WS status dot, update count, book odds age
- One `fight-card` per fight, ordered Main Card → Prelims → Early Prelims
- Each card: markets table (moneyline first, then props collapsed behind toggle)
- Below moneyline rows: **BOOKS bar** showing sportsbook consensus odds + Poly-vs-Book gap
  - If no sportsbook match: shows **POLY IMPLIED** bar with Polymarket prices as American odds (live-updating)
  - If book match arrives later: panel re-renders automatically (dynamic re-render fix)
- Price badges color-coded: green (favorite) → yellow (even) → orange/red (underdog)
- Flash animation on price change

#### Tab 2 — AI Predictions
- Three columns: **ChatGPT** (green), **Gemini** (blue), **Grok** (red)
- Each column: textarea to paste JSON → auto-parses on input → renders fight prediction cards
- JSON persisted to `localStorage` — survives page refresh
- Each fight card shows:
  - Card position badge, weight class, bout number
  - Fighter A vs Fighter B (winner highlighted, loser dimmed)
  - Predicted winner + confidence badge (HIGH/MEDIUM/LOW) with confidence %
  - Win method + round + time
  - Probability bar (green = Fighter A share)
  - Market lines (decimal), Polymarket prob, edge value (color-coded)
  - Bet signal pill: BET A (green) / BET B (blue) / PASS (dim) + one-line logic
  - Collapsible "Analysis" section: key factors, each fighter's path to win, analyst note
- Clear (✕) button per column

---

## JSON Schema for AI Predictions Tab

Each AI should output an array of objects matching this schema:

```json
[
  {
    "fight_id": "UFCFN_STR_01",
    "card_position": "MAIN_CARD | PRELIMS",
    "bout_order": 1,
    "fighter_A": "Full Name",
    "fighter_B": "Full Name",
    "weight_class": "Featherweight",
    "predicted_winner": "Full Name (must match fighter_A or fighter_B exactly)",
    "win_method": "KO/TKO | SUBMISSION | DECISION | SPLIT_DECISION | MAJORITY_DECISION | DQ | NC",
    "predicted_round": 2,
    "predicted_round_time": "2:45",
    "confidence": "HIGH | MEDIUM | LOW",
    "confidence_pct": 0.78,
    "prob_fighter_A_wins": 0.68,
    "prob_fighter_B_wins": 0.32,
    "prob_sum_check": 1.0,
    "market_line_A": 1.67,
    "market_line_B": 2.30,
    "market_implied_prob_A": 0.60,
    "polymarket_prob_A": 0.63,
    "polymarket_volume_usd": 45000,
    "edge_A": 0.08,
    "bet_signal": "BET_A | BET_B | PASS",
    "bet_signal_logic": "One sentence explaining the signal.",
    "key_factors": ["Factor 1", "Factor 2", "Factor 3"],
    "fighter_A_path_to_win": "1-2 sentences.",
    "fighter_B_path_to_win": "1-2 sentences.",
    "analyst_note": "1-2 sentences of qualitative context."
  }
]
```

All fields are optional except `fighter_A`, `fighter_B`, and `predicted_winner` — nulls are handled gracefully.

---

## Key Constants to Know / Change

| Constant | Location (line ~) | Default | Description |
|---|---|---|---|
| `ODDS_REFRESH` | ~58 | `300` | Seconds between sportsbook odds fetches |
| `BOOK_PRIORITY` | ~61 | DraftKings first | Order to pick books for consensus |
| `CARD_ORDER` | ~60 | Main=0, Prelims=1, Early=2 | Fight card sort order |
| `WS_URL` | ~54 | Polymarket WS | WebSocket endpoint |
| `GAMMA_URL` | ~55 | Polymarket Gamma API | REST endpoint for events |
| `ODDS_API_URL` | ~56 | The Odds API v4 | Sportsbook odds endpoint |

---

## Known Issues / Things Left to Do

1. **Book odds name matching** — fuzzy name match (`_name_match`) uses a simple word-overlap approach. If a fighter's name in The Odds API differs significantly from Polymarket's title (e.g. "Jose Aldo" vs "Aldo"), it won't match. Can improve with last-name-only fallback.

3. **No fight-alignment in AI Predictions tab** — the three columns render independently; fights aren't aligned horizontally by `fight_id`. Could add a "Compare" view that matches by `fight_id` and shows all three AIs per row.

4. **No auto-refresh of Polymarket data** — fights are fetched once at startup. If new fights are added to Polymarket during the session they won't appear without a restart. Could add a periodic re-fetch.

5. **`ufc_fight_detail.py` uses `active: true` filter** — some fights that are "inactive" on Polymarket (not yet open for trading) won't appear. The v2 web app uses the same filter so they're consistent, but it's worth knowing.

---

## How the Sportsbook Odds Pipeline Works

```
startup
  └─ fetch_book_odds()                        ← runs immediately, then every 5 min
       └─ GET the-odds-api.com/v4/sports/mma  ← returns all upcoming MMA events
            └─ for each S.fights entry:
                 └─ _fighter_names(title)      ← parse "Fighter A vs. Fighter B" from Poly title
                 └─ _name_match(a, b)          ← fuzzy match to Odds API event
                 └─ build books[] list         ← top 5 books by BOOK_PRIORITY
                 └─ compute consensus_a/b      ← avg implied prob across books
                 └─ compute vig               ← sum of implied probs - 1
                 └─ store in S.book_odds[title]

every SSE tick (0.5s)
  └─ snapshot()
       └─ gap_a = live poly price - consensus_a   ← computed fresh each tick
       └─ sends to browser via /stream
```

---

## How to Add a New Data Column to the Markets Table

1. Add field to `snapshot()` in the `mkts.append({...})` dict
2. Add `<th>` to the `<thead>` in `buildCard()` JS function
3. Add `<td>` to `buildRow()` JS function with `data-role="yourkey"`
4. Add update logic to `updateRow()` JS function

---

## How to Change the SSE Refresh Rate

In the Flask route (line ~445):
```python
time.sleep(0.5)   # change this — 0.5s = 2 updates/sec
```

---

## File Sizes (approx)

- `ufc_fight_detail_ws_app_v2.py` — ~1,500 lines (Python backend + full HTML/CSS/JS template as string)
- The HTML template starts around line 460 and runs to the end of the file
- CSS section: ~350 lines inside the `<style>` block
- JS section: ~400 lines inside the `<script>` block
