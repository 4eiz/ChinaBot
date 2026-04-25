# app/utils/message_utils.py
"""
Утилиты для безопасной работы с сообщениями Telegram.
"""
from __future__ import annotations

import logging
from aiogram import types

logger = logging.getLogger(__name__)


async def safe_delete(message: types.Message) -> None:
    """
    Пытается удалить сообщение.

    Если удаление невозможно (сообщение слишком старое, уже удалено,
    нет прав и т.д.) — тихо пропускает ошибку и продолжает выполнение.
    Это гарантирует, что бот ВСЕГДА отправит следующее сообщение,
    даже если старое удалить не получилось.

    Использование:
        from app.utils import safe_delete

        await safe_delete(call.message)   # вместо await call.message.delete()
        await call.message.answer(...)    # отправляется всегда
    """
    try:
        await message.delete()
    except Exception as exc:
        logger.debug("safe_delete: не удалось удалить сообщение %s: %s", message.message_id, exc)
