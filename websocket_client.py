import asyncio
import json
import threading
import time

import websockets

from config import WS_URL
from state import S


def _apply(msg):
    etype = msg.get("event_type", "")

    if etype == "book":
        token = msg.get("asset_id")
        if token in S.prices:
            bids = msg.get("bids", [])
            asks = msg.get("asks", [])
            bid = max((float(b["price"]) for b in bids), default=None) if bids else None
            ask = min((float(a["price"]) for a in asks), default=None) if asks else None
            S.prices[token]["bid"] = bid
            S.prices[token]["ask"] = ask
            if bid is not None:
                S.prices[token]["price"] = bid
            idx = S.token_to_idx.get(token)
            if idx is not None:
                S.updates[idx] = time.monotonic()
            return True

    elif etype == "price_change":
        changed = False
        for ch in msg.get("changes", []):
            token = ch.get("asset_id")
            p     = ch.get("price")
            if token in S.prices and p is not None:
                S.prices[token]["price"] = float(p)
                idx = S.token_to_idx.get(token)
                if idx is not None:
                    S.updates[idx] = time.monotonic()
                changed = True
        return changed

    elif etype == "last_trade_price":
        token = msg.get("asset_id")
        p     = msg.get("price")
        idx   = S.token_to_idx.get(token)
        if idx is not None and p is not None:
            slot  = S.token_to_slot.get(token, "a")
            label = None
            for fight in S.fights:
                for m in fight["markets"]:
                    if m["idx"] == idx:
                        label = m["label_a"] if slot == "a" else m["label_b"]
                        break
            S.trades[idx] = {"price": float(p), "label": label}
            S.updates[idx] = time.monotonic()
            return True

    return False


async def _heartbeat(ws):
    while True:
        try:
            await asyncio.sleep(10)
            await ws.send("PING")
        except (asyncio.CancelledError, Exception):
            break


async def _ws_loop(token_ids):
    while True:
        try:
            async with websockets.connect(WS_URL) as ws:
                S.ws_connected = True
                await ws.send(json.dumps({
                    "assets_ids": token_ids, "type": "market",
                    "custom_feature_enabled": True,
                }))
                hb = asyncio.create_task(_heartbeat(ws))
                try:
                    async for raw in ws:
                        if raw == "PONG":
                            continue
                        try:
                            data = json.loads(raw)
                        except Exception:
                            continue
                        if not isinstance(data, list):
                            data = [data]
                        for msg in data:
                            if isinstance(msg, dict) and _apply(msg):
                                S.msg_count += 1
                except websockets.exceptions.ConnectionClosed:
                    pass
                finally:
                    hb.cancel()
        except Exception:
            pass
        S.ws_connected = False
        await asyncio.sleep(3)


def start_ws(token_ids):
    def _run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(_ws_loop(token_ids))
    threading.Thread(target=_run, daemon=True).start()
