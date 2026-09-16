"""Binance public market data for ICP. No API key, no account, no signing —
these are open endpoints, which is the whole reason this bot needs no secrets
beyond the Telegram token.
"""
import logging

import httpx

from config import BINANCE_SYMBOL

logger = logging.getLogger(__name__)

BASE_URL = "https://api.binance.com/api/v3"
TIMEOUT_SECONDS = 20


class MarketSnapshot:
    """One 24-hour picture of the market: price, movement, turnover, and which
    side was doing the pushing."""

    def __init__(self, ticker: dict, klines: list[list]):
        self.price = float(ticker["lastPrice"])
        self.open_price = float(ticker["openPrice"])
        self.change_percent = float(ticker["priceChangePercent"])
        self.high = float(ticker["highPrice"])
        self.low = float(ticker["lowPrice"])
        self.volume_coin = float(ticker["volume"])       # in ICP
        self.volume_usd = float(ticker["quoteVolume"])   # in USDT
        self.trades = int(ticker["count"])

        # Binance kline layout, by index:
        #   5 = base volume, 7 = quote volume, 9 = TAKER BUY base volume,
        #   10 = taker buy quote volume.
        # Summing 24 hourly candles matches the rolling 24h window the ticker
        # reports; the daily candle would instead mean "since 00:00 UTC", which
        # would quietly disagree with the percentage next to it.
        self.bought_coin = sum(float(k[9]) for k in klines)
        window_volume = sum(float(k[5]) for k in klines)
        self.sold_coin = max(0.0, window_volume - self.bought_coin)
        self.bought_usd = sum(float(k[10]) for k in klines)
        window_volume_usd = sum(float(k[7]) for k in klines)
        self.sold_usd = max(0.0, window_volume_usd - self.bought_usd)

    @property
    def bought_share(self) -> float:
        total = self.bought_coin + self.sold_coin
        return (self.bought_coin / total * 100) if total else 0.0

    @property
    def sold_share(self) -> float:
        return 100.0 - self.bought_share if (self.bought_coin + self.sold_coin) else 0.0


async def fetch_snapshot() -> MarketSnapshot | None:
    """Both calls in one client session. Returns None on any failure — callers
    are loops and command handlers that must not die over a blip."""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            ticker_resp = await client.get(f"{BASE_URL}/ticker/24hr", params={"symbol": BINANCE_SYMBOL})
            ticker_resp.raise_for_status()
            klines_resp = await client.get(
                f"{BASE_URL}/klines",
                params={"symbol": BINANCE_SYMBOL, "interval": "1h", "limit": 24},
            )
            klines_resp.raise_for_status()
        return MarketSnapshot(ticker_resp.json(), klines_resp.json())
    except Exception:
        logger.exception("Failed to fetch %s market data from Binance", BINANCE_SYMBOL)
        return None
