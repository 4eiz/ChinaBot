# app/utils/message_utils.py
"""
Утилиты для безопасной работы с сообщениями Telegram.
"""
from __future__ import annotations

import logging
from aiogram import types
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

logger = logging.getLogger(__name__)


async def safe_delete(message: types.Message) -> None:
    """
    Пытается удалить сообщение.

    Ошибки Bad Request передаются обработчику обновления: при старом
    или удалённом сообщении он отправляет главное меню.
    Отсутствие доступа к чату пропускается.

    Использование:
        from app.utils import safe_delete

        await safe_delete(call.message)   # вместо await call.message.delete()
        await call.message.answer(...)    # отправляется всегда
    """
    try:
        await message.delete()
    except TelegramBadRequest:
        raise
    except TelegramForbiddenError:
        pass
    except Exception as exc:
        logger.debug(
            "safe_delete: не удалось удалить message_id=%s: %s",
            getattr(message, "message_id", "?"),
            exc,
        )
