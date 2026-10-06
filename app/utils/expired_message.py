"""Recover navigation when Telegram refuses to delete an old message."""
from aiogram import BaseMiddleware
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import DeleteMessage

import config
from database import UsersDB
from keyboards import StartKB
from media import PhotoBank


def is_unavailable_message(exc: Exception) -> bool:
    return (
        isinstance(exc, TelegramBadRequest)
        and isinstance(exc.method, DeleteMessage)
        and any(reason in exc.message.lower() for reason in (
            "message can't be deleted", "message to delete not found",
        ))
    )


class ExpiredMessageMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        try:
            return await handler(event, data)
        except TelegramBadRequest as exc:
            if not is_unavailable_message(exc):
                raise
            call = event.callback_query
            message = call.message if call else event.message
            user = call.from_user if call else (message.from_user if message else None)
            if message is None or user is None:
                raise
            state = data.get("state")
            if state is not None:
                await state.clear()
            users = UsersDB(conn=config.CONNECTION_DATABASE)
            is_admin = bool(await users.is_admin(user_id=user.id))
            await data["bot"].send_photo(
                chat_id=message.chat.id,
                photo=PhotoBank.get_file('MENU_IMAGE'),
                caption=(
                    f"👋 <b>Добро пожаловать в {config.SHOP_NAME}!</b>\n\n"
                    "Выберите раздел ниже:"
                ),
                reply_markup=StartKB.main(is_admin=is_admin),
            )
            if call:
                try:
                    await call.answer()
                except TelegramBadRequest as answer_error:
                    if "query is too old" not in answer_error.message.lower():
                        raise
            return None
