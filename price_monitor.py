"""Background loops: move alerts on several levels, and a daily digest.

The hard part of a threshold alert is not noticing the threshold — it is not
notifying about it fifty times in a row. Each level is a two-state machine
persisted in the database: armed until it fires, re-armed only once the move
retreats past a nearer point — below it for a rise level, above it for a fall
one. That gap stops a price resting on a threshold from ringing every cycle,
and storing it in the database rather than in memory means a restart does not
re-send an alert already delivered.

Levels and their re-arm points live in alert_levels, shared with the one-shot
GitHub Actions script so both behave identically.
"""
import asyncio
import json
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

import database as db
from alert_levels import LEVELS, decide, normalise_state
from config import DIGEST_HOUR, DISPLAY_TZ, POLL_INTERVAL_SECONDS, TELEGRAM_CHAT_ID
from formatting import format_alert, format_snapshot
from icp_client import fetch_snapshot

logger = logging.getLogger(__name__)

# The name predates the fall levels. Renaming it would orphan the stored map
# and re-arm every level at once, so it stays as it is.
ALERT_STATE_KEY = "rise_alert_armed"
LOCAL_TZ = ZoneInfo(DISPLAY_TZ)


async def _recipients() -> list[str]:
    """Individual subscribers plus the group, if one is configured. The group
    is added last and de-duplicated, so someone who is both a subscriber and a
    member of the group does not get the same message twice."""
    chats = [str(chat_id) for chat_id in await db.alert_subscribers()]
    if TELEGRAM_CHAT_ID and TELEGRAM_CHAT_ID not in chats:
        chats.append(TELEGRAM_CHAT_ID)
    return chats


async def _broadcast(bot: Bot, text: str) -> int:
    sent = 0
    for chat_id in await _recipients():
        try:
            await bot.send_message(chat_id, text, parse_mode="HTML")
            sent += 1
        except TelegramAPIError:
            logger.exception("Could not deliver to chat_id=%s", chat_id)
    return sent


async def _load_armed() -> dict:
    raw = await db.get_state(ALERT_STATE_KEY)
    try:
        stored = json.loads(raw) if raw else None
    except json.JSONDecodeError:
        stored = None
    return normalise_state({"armed": stored})


async def price_monitor_loop(bot: Bot) -> None:
    logger.info(
        "Starting ICP price monitor: levels %s, every %ss",
        sorted(LEVELS), POLL_INTERVAL_SECONDS,
    )
    while True:
        try:
            snapshot = await fetch_snapshot()
            if snapshot is not None:
                armed = await _load_armed()
                level, new_armed = decide(snapshot.change_percent, armed)

                if level is not None:
                    sent = await _broadcast(bot, format_alert(snapshot, level))
                    logger.info(
                        "ICP %+.2f%% crossed the %+.0f%% level — alerted %s chat(s)",
                        snapshot.change_percent, level, sent,
                    )
                if new_armed != armed:
                    await db.set_state(ALERT_STATE_KEY, json.dumps(new_armed))
        except Exception:
            logger.exception("Price monitor iteration failed")

        await asyncio.sleep(POLL_INTERVAL_SECONDS)


def _seconds_until_digest() -> float:
    """Next DIGEST_HOUR in the display timezone. Computed fresh every cycle
    rather than by sleeping 24h, so a restart cannot shift the schedule and
    daylight-saving changes elsewhere cannot drift it."""
    now = datetime.now(LOCAL_TZ)
    target = now.replace(hour=DIGEST_HOUR, minute=0, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


async def daily_digest_loop(bot: Bot) -> None:
    logger.info("Starting daily digest loop: %02d:00 %s", DIGEST_HOUR, DISPLAY_TZ)
    while True:
        wait = _seconds_until_digest()
        logger.info("Next ICP digest in %.1f h", wait / 3600)
        await asyncio.sleep(wait)
        try:
            snapshot = await fetch_snapshot()
            if snapshot is None:
                logger.warning("Digest skipped: market data unavailable")
            else:
                sent = await _broadcast(bot, format_snapshot(snapshot))
                logger.info("Daily ICP digest sent to %s chat(s)", sent)
        except Exception:
            logger.exception("Daily digest failed")
        # Guard against a fast failure looping straight back into the same hour.
        await asyncio.sleep(60)
