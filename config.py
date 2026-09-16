"""Environment configuration, validated at import time.

Everything that can be wrong with a pasted secret is checked here and fails
loudly at startup, rather than surfacing later as a silent no-op deep inside
an SDK call.
"""
import logging
import os

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


def _ascii_only(name: str, value: str) -> str:
    """Secrets go straight into HTTP headers, which are ASCII-encoded. A value
    pasted with smart quotes, a trailing newline or Cyrillic look-alikes throws
    UnicodeEncodeError somewhere far from the cause. Catch it here."""
    if not value:
        return value
    try:
        value.encode("ascii")
    except UnicodeEncodeError:
        bad = [i for i, ch in enumerate(value) if ord(ch) > 127]
        logger.error(
            "%s contains %d non-ASCII character(s) (first at index %s) — "
            "re-enter it as plain ASCII. Continuing without it.",
            name, len(bad), bad[0] if bad else "?",
        )
        return ""
    return value


# .strip() everywhere: Railway's variable editor happily stores a trailing
# space or newline, and it silently breaks token comparisons.
TELEGRAM_BOT_TOKEN = _ascii_only("TELEGRAM_BOT_TOKEN", os.getenv("TELEGRAM_BOT_TOKEN", "").strip())

ADMIN_CHAT_IDS = {
    int(x) for x in os.getenv("ADMIN_CHAT_IDS", "").split(",") if x.strip().lstrip("-").isdigit()
}

DATABASE_PATH = os.getenv("DATABASE_PATH", "./bot.db").strip()
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").strip().upper()

ANTHROPIC_API_KEY = _ascii_only("ANTHROPIC_API_KEY", os.getenv("ANTHROPIC_API_KEY", "").strip())
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5").strip()
AI_ENABLED = bool(ANTHROPIC_API_KEY)

if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN is not set — add it to .env")


# --- Market data (Binance public API, no key required) ---
BINANCE_SYMBOL = os.getenv("BINANCE_SYMBOL", "ICPUSDT").strip().upper()

# How often the 24h move is checked. Binance's public rate limits are far above
# this; 60s is simply enough resolution for a 24-hour percentage.
POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", "60"))

# Fire an alert once the 24h change reaches this, then stay silent until it
# drops back under ALERT_REARM_PERCENT. Without that gap a price sitting at
# exactly the threshold would alert on every single poll.
ALERT_THRESHOLD_PERCENT = float(os.getenv("ALERT_THRESHOLD_PERCENT", "10"))
ALERT_REARM_PERCENT = float(os.getenv("ALERT_REARM_PERCENT", "8"))
