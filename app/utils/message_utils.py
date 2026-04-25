"""Утилиты для работы с сообщениями Telegram."""
from __future__ import annotations

import logging
from typing import Union

from aiogram import types
from aiogram.exceptions import TelegramBadRequest

logger = logging.getLogger(__name__)


async def safe_delete(
    target: Union[types.Message, types.CallbackQuery],
) -> bool:
    """
    Безопасно удаляет сообщение: если удалить нельзя (старое / уже удалено /
    нет прав) — просто пропускает ошибку и возвращает False.

    Принимает Message или CallbackQuery (тогда удаляет call.message).

    Возвращает True при успешном удалении, False при пропуске.
    """
    msg: types.Message = (
        target.message if isinstance(target, types.CallbackQuery) else target
    )
    if msg is None:
        return False
    try:
        await msg.delete()
        return True
    except TelegramBadRequest as exc:
        _text = str(exc).lower()
        if any(marker in _text for marker in (
            "message to delete not found",
            "message can't be deleted",
            "message is too old",
        )):
            logger.debug("safe_delete: skip — %s", exc)
            return False
        raise  # неожиданная ошибка — пробрасываем
    except Exception as exc:
        logger.warning("safe_delete: unexpected error — %s", exc)
        return False
