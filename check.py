"""One-shot ICP check, built for GitHub Actions.

Standard library only — no pip install step in the workflow, nothing to break
when a dependency releases a new version, and a run that finishes in seconds.

Two modes:
  python check.py alert    — post only if ICP is up by the threshold (default)
  python check.py digest   — always post the 24h snapshot

State lives in state.json, committed back to the repo by the workflow. A cron
job has no memory between runs, and without memory a price sitting above the
threshold would alert on every single run. Same two-state machine as the
always-on bot: armed until it fires, re-armed only once the move falls back
below the lower re-arm level.
"""
import json
import os
import sys
import urllib.parse
import urllib.request

from formatting import format_alert, format_snapshot

BINANCE = "https://api.binance.com/api/v3"
SYMBOL = os.getenv("BINANCE_SYMBOL", "ICPUSDT")
THRESHOLD = float(os.getenv("ALERT_THRESHOLD_PERCENT", "10"))
REARM = float(os.getenv("ALERT_REARM_PERCENT", "8"))
STATE_FILE = "state.json"
TIMEOUT = 25


def _get_json(url: str, params: dict):
    full = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(full, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


class Snapshot:
    """Same attribute names as icp_client.MarketSnapshot, so formatting.py can
    render either one."""

    def __init__(self, ticker: dict, klines: list):
        self.price = float(ticker["lastPrice"])
        self.open_price = float(ticker["openPrice"])
        self.change_percent = float(ticker["priceChangePercent"])
        self.high = float(ticker["highPrice"])
        self.low = float(ticker["lowPrice"])
        self.volume_coin = float(ticker["volume"])
        self.volume_usd = float(ticker["quoteVolume"])
        self.trades = int(ticker["count"])

        # Kline indexes: 5 = base volume, 7 = quote volume,
        # 9 = taker BUY base volume, 10 = taker buy quote volume.
        self.bought_coin = sum(float(k[9]) for k in klines)
        self.sold_coin = max(0.0, sum(float(k[5]) for k in klines) - self.bought_coin)
        self.bought_usd = sum(float(k[10]) for k in klines)
        self.sold_usd = max(0.0, sum(float(k[7]) for k in klines) - self.bought_usd)

    @property
    def bought_share(self) -> float:
        total = self.bought_coin + self.sold_coin
        return (self.bought_coin / total * 100) if total else 0.0

    @property
    def sold_share(self) -> float:
        return 100.0 - self.bought_share if (self.bought_coin + self.sold_coin) else 0.0


def fetch() -> Snapshot:
    ticker = _get_json(f"{BINANCE}/ticker/24hr", {"symbol": SYMBOL})
    klines = _get_json(f"{BINANCE}/klines", {"symbol": SYMBOL, "interval": "1h", "limit": 24})
    return Snapshot(ticker, klines)


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
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    if not body.get("ok"):
        # Never print the response verbatim: on some errors Telegram echoes the
        # request URL, which carries the bot token.
        raise RuntimeError(f"Telegram rejected the message: {body.get('description')}")


def read_state() -> dict:
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"armed": True}


def write_state(state: dict) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
        f.write("\n")


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "alert"
    snapshot = fetch()
    print(f"{SYMBOL}: {snapshot.price:.3f} ({snapshot.change_percent:+.2f}% 24h), mode={mode}")

    if mode == "digest":
        send(format_snapshot(snapshot))
        print("Digest sent.")
        return 0

    state = read_state()
    armed = bool(state.get("armed", True))

    if snapshot.change_percent >= THRESHOLD and armed:
        send(format_alert(snapshot, THRESHOLD))
        write_state({"armed": False, "last_alert_change": round(snapshot.change_percent, 2)})
        print(f"Alert sent at {snapshot.change_percent:+.2f}%; disarmed.")
    elif snapshot.change_percent < REARM and not armed:
        write_state({"armed": True})
        print(f"Back to {snapshot.change_percent:+.2f}%; re-armed.")
    else:
        print(f"No action (armed={armed}, threshold={THRESHOLD}%, re-arm={REARM}%).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
