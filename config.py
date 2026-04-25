import os


def _load_dotenv():
    try:
        import _baked_env
        for k, v in _baked_env.SECRETS.items():
            os.environ.setdefault(k, v)
        return
    except ImportError:
        pass
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    try:
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())
    except FileNotFoundError:
        pass


_load_dotenv()

WS_URL       = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
GAMMA_URL    = "https://gamma-api.polymarket.com/events"
ODDS_API_URL = "https://api.the-odds-api.com/v4/sports/mma_mixed_martial_arts/odds/"
ODDS_API_KEY = os.environ.get("ODDS_API_KEY", "")
ODDS_REFRESH = 300   # seconds between book-odds refreshes (~12/hr, free-tier safe)

CARD_ORDER    = {"Main Card": 0, "Main card": 0, "Prelims": 1, "Early Prelims": 2}
BOOK_PRIORITY = ["draftkings", "fanduel", "betmgm", "caesars", "pointsbetus",
                 "williamhill_us", "bovada", "mybookieag"]
