"""One-shot ICP check, built for GitHub Actions.

Standard library only — no pip install step, nothing to break when a dependency
releases a new version, and a run that finishes in seconds.

Why not Binance, which is the obvious choice: it answers 451 "Service
unavailable from a restricted location" to US IP addresses, and GitHub's hosted
runners are in the US. Verified on a real runner, not assumed. Binance.US does
answer, but its ICP book is nearly empty — the turnover and the buy/sell ratio
taken from it would be noise. So:

  CoinGecko  — price, 24h change and GLOBAL turnover across all venues.
  Coinbase   — 24h high/low, venue volume, and per-trade buy/sell side.

Two modes:
  python check.py alert    — post only if ICP crossed a level (see alert_levels)
  python check.py digest   — always post the 24h snapshot

State lives in state.json, committed back by the workflow: a cron job has no
memory between runs, and without memory a price sitting above a level would
alert on every single run.
"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

from alert_levels import LEVELS, decide, normalise_state
from formatting import format_alert, format_snapshot

COINBASE = "https://api.exchange.coinbase.com"
COINGECKO = "https://api.coingecko.com/api/v3"
PRODUCT = os.getenv("COINBASE_PRODUCT", "ICP-USD")
GECKO_ID = os.getenv("COINGECKO_ID", "internet-computer")

# How many recent trades to read for the buy/sell split. A full 24 hours would
# mean ~85k trades and dozens of paginated requests every run, which is far too
# heavy for a job that runs every half hour. One page of the most recent trades
# answers "who is pushing right now", and the message says exactly that rather
# than implying a 24-hour figure.
TRADE_SAMPLE = int(os.getenv("TRADE_SAMPLE", "1000"))

# Times are shown where the reader lives, not where the runner happens to be:
# a GitHub runner thinks in UTC, which tells a reader in Tashkent nothing.
LOCAL_TZ = ZoneInfo(os.getenv("DISPLAY_TZ", "Asia/Tashkent"))
TZ_LABEL = str(LOCAL_TZ).split("/")[-1].replace("_", " ")

STATE_FILE = "state.json"
TIMEOUT = 25
# Some of these endpoints sit behind Cloudflare and reject urllib's default
# User-Agent outright.
HEADERS = {"Accept": "application/json", "User-Agent": "icp-watcher/1.0"}


def _get_json(url: str, params: dict | None = None):
    full = f"{url}?{urllib.parse.urlencode(params)}" if params else url
    req = urllib.request.Request(full, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


class Snapshot:
    def __init__(self, gecko: dict, stats: dict, trades: list):
        g = gecko.get(GECKO_ID, {})
        self.price = float(g.get("usd") or stats["last"])
        self.change_percent = float(g.get("usd_24h_change") or 0.0)
        self.market_cap = float(g.get("usd_market_cap") or 0.0)
        # Global turnover in dollars: what the whole market traded, not one venue.
        self.volume_usd = float(g.get("usd_24h_vol") or 0.0)

        self.high = float(stats["high"])
        self.low = float(stats["low"])
        self.open_price = float(stats["open"])
        # Venue volume, in ICP, on Coinbase alone.
        self.venue_volume_coin = float(stats["volume"])

        self.trade_count = len(trades)
        self.bought_coin = sum(float(t["size"]) for t in trades if t.get("side") == "buy")
        self.sold_coin = sum(float(t["size"]) for t in trades if t.get("side") == "sell")
        self.bought_usd = sum(
            float(t["size"]) * float(t["price"]) for t in trades if t.get("side") == "buy"
        )
        self.sold_usd = sum(
            float(t["size"]) * float(t["price"]) for t in trades if t.get("side") == "sell"
        )

    @property
    def bought_share(self) -> float:
        total = self.bought_coin + self.sold_coin
        return (self.bought_coin / total * 100) if total else 0.0

    @property
    def sold_share(self) -> float:
        return 100.0 - self.bought_share if (self.bought_coin + self.sold_coin) else 0.0


def fetch() -> Snapshot:
    gecko = _get_json(
        f"{COINGECKO}/simple/price",
        {
            "ids": GECKO_ID,
            "vs_currencies": "usd",
            "include_market_cap": "true",
            "include_24hr_vol": "true",
            "include_24hr_change": "true",
        },
    )
    stats = _get_json(f"{COINBASE}/products/{PRODUCT}/stats")
    trades = _get_json(f"{COINBASE}/products/{PRODUCT}/trades", {"limit": TRADE_SAMPLE})
    snapshot = Snapshot(gecko, stats, trades)
    snapshot.generated_at = (
        f"{datetime.now(LOCAL_TZ).strftime('%d.%m.%Y %H:%M')} ({TZ_LABEL})"
    )
    return snapshot


def send(text: str) -> None:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    payload = json.dumps({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        # Never surface the exception verbatim: its URL carries the bot token.
        detail = ""
        try:
            detail = json.loads(e.read().decode("utf-8")).get("description", "")
        except Exception:
            pass
        raise RuntimeError(f"Telegram returned {e.code}: {detail}") from None
    if not body.get("ok"):
        raise RuntimeError(f"Telegram rejected the message: {body.get('description')}")


def read_state() -> dict:
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def write_state(state: dict) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
        f.write("\n")


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "alert"

    snapshot = fetch()
    print(
        f"ICP {snapshot.price:.3f} ({snapshot.change_percent:+.2f}% 24h), "
        f"mode={mode}, levels={sorted(LEVELS)}"
    )

    if mode == "digest":
        send(format_snapshot(snapshot))
        print("Digest sent.")
        return 0

    armed = normalise_state(read_state())
    level, new_armed = decide(snapshot.change_percent, armed)

    if level is not None:
        send(format_alert(snapshot, level))
        print(f"Alert sent for the {level:+.0f}% level at {snapshot.change_percent:+.2f}%.")
    if new_armed != armed:
        write_state({"armed": new_armed, "last_change": round(snapshot.change_percent, 2)})
        print(f"Armed levels now: {new_armed}")
    elif level is None:
        print(f"No action. Armed levels: {armed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
