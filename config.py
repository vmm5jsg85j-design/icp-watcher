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


# --- Market data (public endpoints, no key required) ---
# See icp_client for why these two and not Binance.
COINGECKO_ID = os.getenv("COINGECKO_ID", "internet-computer").strip()
COINBASE_PRODUCT = os.getenv("COINBASE_PRODUCT", "ICP-USD").strip().upper()

# How many recent trades the buy/sell split is taken from. A full 24 hours is
# ~85k trades and dozens of paginated requests; one page answers "who is
# pushing right now", and the message says exactly that.
TRADE_SAMPLE = int(os.getenv("TRADE_SAMPLE", "1000"))

# How often the 24h move is checked. 60s is ample resolution for a figure that
# covers a whole day, and keeps well inside both vendors' rate limits.
POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", "60"))

# Alert levels live in alert_levels.LEVELS: they are logic, not deployment
# configuration, and each level belongs next to its own re-arm point.

# --- Delivery ---
# Optional group or channel that gets alerts and the daily digest in addition
# to individual subscribers. Empty means personal chats only.
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

# Times are shown where the reader lives, not where the server happens to run.
DISPLAY_TZ = os.getenv("DISPLAY_TZ", "Asia/Tashkent").strip()
DIGEST_HOUR = int(os.getenv("DIGEST_HOUR", "9"))
