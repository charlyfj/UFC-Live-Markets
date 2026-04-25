"""
UFC Fight Market Live Observer v5 — adds Live Markets data into Fights Analysis.

Setup:
    pip install flask requests websockets
    python ufc_fight_detail_ws_app_v5.py [--date YYYY-MM-DD] [--port 5000]
"""

import argparse
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


_base = sys._MEIPASS if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
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
    ap = argparse.ArgumentParser(description="UFC Polymarket Live v5")
    ap.add_argument("--date", help="Card date (YYYY-MM-DD). Default: nearest upcoming card.")
    ap.add_argument("--port", type=int, default=5000)
    args = ap.parse_args()

    target = Date.fromisoformat(args.date) if args.date else None
    print(f"Fetching UFC fights{' for ' + args.date if args.date else ' (nearest upcoming card)'}…")

    token_ids     = load_state(target)
    date_str      = S.saturday.strftime("%A, %B %d %Y") if S.saturday else "unknown date"
    fights_count  = len(S.fights)
    markets_count = sum(len(f["markets"]) for f in S.fights)
    print(f"Card: {date_str}  |  {fights_count} fights · {markets_count} markets · {len(token_ids)} token streams")

    if ODDS_API_KEY:
        print("Starting book-odds thread…")
        start_odds_thread()
    else:
        print("ODDS_API_KEY not set — sportsbook odds panel will show setup hint.")

    start_ws(token_ids)
    print(f"Open http://localhost:{args.port}")
    app.run(host="0.0.0.0", port=args.port, threaded=True, debug=False)
