"""Logging with secrets redacted on the way out.

Learned the hard way on the previous bot: httpx logs the full URL of every
request at INFO, and any API that takes its key as a `?token=` query parameter
therefore prints that key into every single log line. Silencing httpx hides the
key but also hides the only signal that the poll loops are alive, so redact
instead. Done in the Formatter rather than a Filter so it also covers exception
tracebacks, where a failing request's URL surfaces too.
"""
import logging
import re

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

_QUERY_SECRET_RE = re.compile(r"\b(token|api[-_]?key|apikey|access_token)=[^&\s\"']+", re.IGNORECASE)
_TELEGRAM_TOKEN_RE = re.compile(r"/bot(\d+):[A-Za-z0-9_-]+")


def redact_secrets(text: str) -> str:
    text = _QUERY_SECRET_RE.sub(lambda m: m.group(1) + "=***", text)
    # Keep the numeric bot id: it is not a secret and it helps read the logs.
    return _TELEGRAM_TOKEN_RE.sub(r"/bot\1:***", text)


class RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return redact_secrets(super().format(record))


def setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(level=getattr(logging, level, logging.INFO), format=LOG_FORMAT)
    for handler in logging.getLogger().handlers:
        handler.setFormatter(RedactingFormatter(LOG_FORMAT))
