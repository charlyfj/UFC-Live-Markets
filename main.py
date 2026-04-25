"""
UFC Fight Market Live Observer v5 — adds Live Markets data into Fights Analysis.

For Railway deployment:
    - Set environment variable: ODDS_API_KEY (if using odds)
    - Railway will provide $PORT automatically
"""

import os
import sys
import time
from datetime import date as Date

from flask import Flask, Response, render_template

from config import ODDS_API_KEY
from odds import start_odds_thread
from polymarket import load_state, snapshot
from state import S
from websocket_client import start_ws


_base = os.path.dirname(os.path.abspath(__file__))
if getattr(sys, "frozen", False):  # for PyInstaller (if you still use it)
    _base = sys._MEIPASS

app = Flask(__name__, template_folder=os.path.join(_base, "templates"))


@app.route("/")
def index():
    return render_template("index_v5.html")


@app.route("/stream")
def stream():
    def generate():
        try:
            while True:
                yield f"data: {snapshot()}\n\n"
                time.sleep(0.5)
        except GeneratorExit:
            pass
    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


if __name__ == "__main__":
    # === Railway / Production settings ===
    port = int(os.environ.get("PORT", 5000))   # Railway injects $PORT
    debug = os.environ.get("FLASK_DEBUG", "False").lower() == "true"

    # Optional: still support local --date flag for development
    import argparse
    import sys
    ap = argparse.ArgumentParser(description="UFC Polymarket Live v5")
    ap.add_argument("--date", help="Card date (YYYY-MM-DD). Default: nearest upcoming card.")
    args, _ = ap.parse_known_args()   # ignore unknown args from Railway

    target = Date.fromisoformat(args.date) if args.date else None
    print(f"Fetching UFC fights{' for ' + args.date if args.date else ' (nearest upcoming card)'}…")

    token_ids     = load_state(target)
    date_str      = S.saturday.strftime("%A, %B %d %Y") if S.saturday else "unknown date"
    fights_count  = len(S.fights)
    markets_count = sum(len(f.get("markets", [])) for f in S.fights)
    print(f"Card: {date_str}  |  {fights_count} fights · {markets_count} markets · {len(token_ids)} token streams")

    if ODDS_API_KEY:
        print("Starting book-odds thread…")
        start_odds_thread()
    else:
        print("ODDS_API_KEY not set — sportsbook odds panel will show setup hint.")

    start_ws(token_ids)

    print(f"Starting server on http://0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port, threaded=True, debug=debug)