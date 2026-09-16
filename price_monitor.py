"""Background loop that watches the 24h move and fires one alert per event.

The hard part of a threshold alert is not noticing the threshold — it is not
notifying about it fifty times in a row. So the loop is a two-state machine
stored in the database: it is ARMED until it fires, and it re-arms only once
the move falls back under a lower re-arm level. That hysteresis gap is what
stops a price hovering at exactly 10% from ringing every single cycle, and
storing the state (rather than keeping it in memory) means a restart doesn't
re-fire an alert the user already received.
"""
import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

import database as db
from config import ALERT_REARM_PERCENT, ALERT_THRESHOLD_PERCENT, POLL_INTERVAL_SECONDS
from formatting import format_alert
from icp_client import fetch_snapshot

logger = logging.getLogger(__name__)

ALERT_STATE_KEY = "rise_alert_armed"


async def _is_armed() -> bool:
    # Default to armed on a fresh database: the first qualifying move should alert.
    return (await db.get_state(ALERT_STATE_KEY) or "1") == "1"


async def price_monitor_loop(bot: Bot) -> None:
    logger.info(
        "Starting ICP price monitor: alert above +%.1f%%, re-arm below +%.1f%%, every %ss",
        ALERT_THRESHOLD_PERCENT, ALERT_REARM_PERCENT, POLL_INTERVAL_SECONDS,
    )
    while True:
        try:
            snapshot = await fetch_snapshot()
            if snapshot is not None:
                armed = await _is_armed()

                if snapshot.change_percent >= ALERT_THRESHOLD_PERCENT and armed:
                    logger.info("ICP up %.2f%% — firing alert", snapshot.change_percent)
                    text = format_alert(snapshot, ALERT_THRESHOLD_PERCENT)
                    for chat_id in await db.alert_subscribers():
                        try:
                            await bot.send_message(chat_id, text, parse_mode="HTML")
                        except TelegramAPIError:
                            logger.exception("Failed to send alert to chat_id=%s", chat_id)
                    await db.set_state(ALERT_STATE_KEY, "0")

                elif snapshot.change_percent < ALERT_REARM_PERCENT and not armed:
                    logger.info("ICP back to %.2f%% — alert re-armed", snapshot.change_percent)
                    await db.set_state(ALERT_STATE_KEY, "1")
        except Exception:
            logger.exception("Price monitor iteration failed")

        await asyncio.sleep(POLL_INTERVAL_SECONDS)
