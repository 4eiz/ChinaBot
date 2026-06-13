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

    Если удаление невозможно (сообщение старше 48 ч, уже удалено,
    нет прав, flood wait и т.д.) — тихо пропускает ошибку.

    Бот ВСЕГДА продолжает выполнение и отправляет следующее сообщение
    — независимо от результата удаления.

    Использование:
        from app.utils import safe_delete

        await safe_delete(call.message)   # вместо await call.message.delete()
        await call.message.answer(...)    # отправляется всегда
    """
    try:
        await message.delete()
    except (TelegramBadRequest, TelegramForbiddenError):
        pass
    except Exception as exc:
        logger.debug(
            "safe_delete: не удалось удалить message_id=%s: %s",
            getattr(message, "message_id", "?"),
            exc,
        )
