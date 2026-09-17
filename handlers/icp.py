import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

import database as db
from formatting import format_snapshot
from icp_client import fetch_snapshot

logger = logging.getLogger(__name__)
router = Router()


@router.message(Command("icp", "price"))
async def cmd_icp(message: Message) -> None:
    snapshot = await fetch_snapshot()
    if snapshot is None:
        await message.answer("Не удалось получить данные с Binance. Попробуйте через минуту.")
        return
    await message.answer(format_snapshot(snapshot))


@router.message(Command("alerts"))
async def cmd_alerts(message: Message) -> None:
    """/alerts on|off — per-user switch, so one person muting doesn't mute everyone."""
    parts = (message.text or "").split()
    arg = parts[1].lower() if len(parts) > 1 else ""

    if arg in ("on", "вкл"):
        await db.set_alerts(message.chat.id, True)
        await message.answer("🔔 Уведомления о резких движениях включены.")
    elif arg in ("off", "выкл"):
        await db.set_alerts(message.chat.id, False)
        await message.answer("🔕 Уведомления отключены. Вернуть — /alerts on")
    else:
        state = "включены" if await db.alerts_enabled(message.chat.id) else "отключены"
        await message.answer(f"Уведомления сейчас {state}.\nПереключить: /alerts on или /alerts off")
