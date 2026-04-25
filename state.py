class _State:
    def __init__(self):
        self.saturday      = None
        self.fights        = []
        self.ws_connected  = False
        self.msg_count     = 0
        self.prices        = {}   # token_id -> {price, bid, ask}
        self.updates       = {}   # market_idx -> monotonic ts
        self.trades        = {}   # market_idx -> {price, label}
        self.token_to_idx  = {}   # token_id -> market_idx
        self.token_to_slot = {}   # token_id -> "a"|"b"
        self.book_odds     = {}   # fight_title -> book-odds dict
        self.odds_fetched  = None # wall-clock ts of last successful fetch


S = _State()
