import logging

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

import database as db
from config import ADMIN_CHAT_IDS

logger = logging.getLogger(__name__)
router = Router()


def is_admin(chat_id: int) -> bool:
    return chat_id in ADMIN_CHAT_IDS


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await db.add_user(message.chat.id, message.from_user.username if message.from_user else None)
    await message.answer(
        "Бот следит за Internet Computer (ICP).\n\n"
        "/icp — курс, оборот и кто был активнее за 24 часа\n"
        "Уведомление придёт само, если ICP вырастет на 10% за сутки.\n\n"
        "/help — все команды"
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    lines = [
        "<b>Команды</b>",
        "/icp — курс, оборот и соотношение покупок/продаж за 24 часа",
        "/alerts on|off — уведомления о резком росте",
        "/start — начало работы",
        "/help — эта справка",
        "/whoami — показать мой chat_id",
    ]
    if is_admin(message.chat.id):
        lines += ["", "<b>Админские</b>", "/users — сколько пользователей"]
    await message.answer("\n".join(lines))


@router.message(Command("whoami"))
async def cmd_whoami(message: Message) -> None:
    # Deliberately available to everyone: the usual reason someone runs this is
    # to find the chat_id they need to put into ADMIN_CHAT_IDS in the first place.
    await message.answer(f"chat_id: <code>{message.chat.id}</code>")


@router.message(Command("users"))
async def cmd_users(message: Message) -> None:
    if not is_admin(message.chat.id):
        return  # Silent: don't advertise admin commands to strangers.
    await message.answer(f"Пользователей: {len(await db.all_users())}")
