"""Market data for ICP, from sources that answer everywhere.

Binance is the obvious choice and the wrong one here: it replies 451 "Service
unavailable from a restricted location" to US IP addresses, and this runs on a
US-hosted worker. Verified against a real US host, not assumed. Binance.US does
answer, but its ICP book is nearly empty, so turnover and the buy/sell ratio
taken from it would be noise.

  CoinGecko — price, 24h change, market cap and GLOBAL turnover across venues.
  Coinbase  — 24h high/low, venue volume, and the per-trade maker side, from
              which the taker side is derived below.

check.py talks to the same two endpoints over the standard library, because a
GitHub Actions job should not need a pip install. That duplication is
deliberate and small; the wording both produce lives in formatting.py, so the
two cannot drift apart in what they say.
"""
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

from config import COINBASE_PRODUCT, COINGECKO_ID, DISPLAY_TZ, TRADE_SAMPLE

logger = logging.getLogger(__name__)

COINBASE = "https://api.exchange.coinbase.com"
COINGECKO = "https://api.coingecko.com/api/v3"
TIMEOUT_SECONDS = 25
# Both sit behind Cloudflare, which rejects some default clients outright.
HEADERS = {"Accept": "application/json", "User-Agent": "icp-watcher/1.0"}

LOCAL_TZ = ZoneInfo(DISPLAY_TZ)
TZ_LABEL = DISPLAY_TZ.split("/")[-1].replace("_", " ")


class MarketSnapshot:
    """Attribute names match check.Snapshot so formatting.py renders either."""

    def __init__(self, gecko: dict, stats: dict, trades: list):
        g = gecko.get(COINGECKO_ID, {})
        self.price = float(g.get("usd") or stats["last"])
        self.change_percent = float(g.get("usd_24h_change") or 0.0)
        self.market_cap = float(g.get("usd_market_cap") or 0.0)
        self.volume_usd = float(g.get("usd_24h_vol") or 0.0)

        self.high = float(stats["high"])
        self.low = float(stats["low"])
        self.open_price = float(stats["open"])
        self.venue_volume_coin = float(stats["volume"])

        self.trade_count = len(trades)

        # Coinbase reports `side` as the MAKER's side — the order that was
        # already resting on the book. A trade tagged "buy" hit a resting bid,
        # so the TAKER was selling; "sell" means the taker bought. Verified
        # against the tape: across 1000 trades, "buy" came with a down-tick 307
        # times to 72 up-ticks, "sell" with an up-tick 297 to 59. Binance's
        # taker-buy volume, which this replaced, meant the opposite, and
        # reading one as the other inverts the entire buy/sell split.
        taker_bought = [t for t in trades if t.get("side") == "sell"]
        taker_sold = [t for t in trades if t.get("side") == "buy"]

        self.bought_coin = sum(float(t["size"]) for t in taker_bought)
        self.sold_coin = sum(float(t["size"]) for t in taker_sold)
        self.bought_usd = sum(float(t["size"]) * float(t["price"]) for t in taker_bought)
        self.sold_usd = sum(float(t["size"]) * float(t["price"]) for t in taker_sold)
        self.generated_at = f"{datetime.now(LOCAL_TZ).strftime('%d.%m.%Y %H:%M')} ({TZ_LABEL})"

    @property
    def bought_share(self) -> float:
        total = self.bought_coin + self.sold_coin
        return (self.bought_coin / total * 100) if total else 0.0

    @property
    def sold_share(self) -> float:
        return 100.0 - self.bought_share if (self.bought_coin + self.sold_coin) else 0.0


async def fetch_snapshot() -> MarketSnapshot | None:
    """Returns None on any failure: the callers are a background loop and a
    command handler, and neither should die over a blip at one vendor."""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS, headers=HEADERS) as client:
            gecko_resp = await client.get(
                f"{COINGECKO}/simple/price",
                params={
                    "ids": COINGECKO_ID,
                    "vs_currencies": "usd",
                    "include_market_cap": "true",
                    "include_24hr_vol": "true",
                    "include_24hr_change": "true",
                },
            )
            gecko_resp.raise_for_status()

            stats_resp = await client.get(f"{COINBASE}/products/{COINBASE_PRODUCT}/stats")
            stats_resp.raise_for_status()

            trades_resp = await client.get(
                f"{COINBASE}/products/{COINBASE_PRODUCT}/trades", params={"limit": TRADE_SAMPLE}
            )
            trades_resp.raise_for_status()

        return MarketSnapshot(gecko_resp.json(), stats_resp.json(), trades_resp.json())
    except Exception:
        logger.exception("Failed to fetch ICP market data")
        return None
