import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, BotCommandScopeChat, BotCommandScopeDefault

from alert_levels import FALL_LEVELS, RISE_LEVELS
from config import ADMIN_CHAT_IDS, DIGEST_HOUR, DISPLAY_TZ, LOG_LEVEL, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from database import init_db
from handlers.basic import router as basic_router
from handlers.icp import router as icp_router
from logging_setup import setup_logging
from price_monitor import daily_digest_loop, price_monitor_loop

setup_logging(LOG_LEVEL)
logger = logging.getLogger(__name__)

PUBLIC_COMMANDS = [
    BotCommand(command="icp", description="Курс и оборот ICP за 24 часа"),
    BotCommand(command="alerts", description="Уведомления о росте: on / off"),
    BotCommand(command="start", description="Начало работы"),
    BotCommand(command="help", description="Справка"),
    BotCommand(command="whoami", description="Показать мой chat_id"),
]

# Admin commands are gated in their handlers regardless; keeping them out of the
# default menu just stops every regular user from seeing they exist.
ADMIN_COMMANDS = PUBLIC_COMMANDS + [
    BotCommand(command="users", description="Сколько пользователей (админ)"),
]


async def main() -> None:
    await init_db()

    bot = Bot(token=TELEGRAM_BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(basic_router)
    dp.include_router(icp_router)

    if not ADMIN_CHAT_IDS:
        logger.warning("ADMIN_CHAT_IDS is empty — no one can use admin commands. Send /whoami to the bot.")
    logger.info(
        "Alert levels over 24h: rise %s%%, fall %s%%",
        sorted(RISE_LEVELS), sorted(FALL_LEVELS),
    )
    logger.info("Daily digest at %02d:00 %s", DIGEST_HOUR, DISPLAY_TZ)
    if TELEGRAM_CHAT_ID:
        logger.info("Group delivery enabled: %s", TELEGRAM_CHAT_ID)
    else:
        logger.info("Group delivery disabled (TELEGRAM_CHAT_ID not set)")

    # Drops anything queued while the bot was down. Without this a restart after
    # an outage replays every message users sent in the meantime.
    await bot.delete_webhook(drop_pending_updates=True)

    await bot.set_my_commands(PUBLIC_COMMANDS, scope=BotCommandScopeDefault())
    for admin_chat_id in ADMIN_CHAT_IDS:
        try:
            await bot.set_my_commands(ADMIN_COMMANDS, scope=BotCommandScopeChat(chat_id=admin_chat_id))
        except TelegramAPIError:
            logger.exception("Failed to set admin command menu for chat_id=%s", admin_chat_id)

    logger.info("Starting polling and price monitor")
    await asyncio.gather(
        dp.start_polling(bot),
        price_monitor_loop(bot),
        daily_digest_loop(bot),
    )


if __name__ == "__main__":
    asyncio.run(main())
