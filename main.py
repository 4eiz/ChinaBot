import asyncio
import html
import logging
import os
import time
import traceback

from aiogram import Dispatcher
from aiogram.types import ErrorEvent

import config
from app.handlers.services.site_outbox import SiteOutboxPoller
from app.routers import get_routers
from database import CargoService, UsersDB


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)
_last_error_notification_at = 0.0


def _admin_error_chat_ids() -> list[str]:
    raw_ids = [config.ADMIN_CHAT_ID, config.ADMIN_ID, config.ADMIN_FORM_CHAT_ID]
    result = []
    seen = set()

    for raw in raw_ids:
        if not raw:
            continue
        for chat_id in str(raw).replace(";", ",").split(","):
            chat_id = chat_id.strip()
            if chat_id and chat_id not in seen:
                seen.add(chat_id)
                result.append(chat_id)

    return result


async def notify_admins_about_error(event: ErrorEvent) -> None:
    global _last_error_notification_at

    chat_ids = _admin_error_chat_ids()
    if not chat_ids:
        logger.warning("Admin error notification skipped: ADMIN_CHAT_ID/ADMIN_ID is empty")
        return

    now = time.monotonic()
    cooldown = int(os.getenv("ERROR_NOTIFY_COOLDOWN_SECONDS", "30") or "30")
    if now - _last_error_notification_at < cooldown:
        return
    _last_error_notification_at = now

    exc = event.exception
    update_id = getattr(event.update, "update_id", "unknown")
    trace = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    trace = trace[-3000:]
    text = (
        "<b>Bot error</b>\n"
        f"Update ID: <code>{html.escape(str(update_id))}</code>\n"
        f"Type: <code>{html.escape(type(exc).__name__)}</code>\n"
        f"Message: <code>{html.escape(str(exc))}</code>\n\n"
        f"<pre>{html.escape(trace)}</pre>"
    )

    for chat_id in chat_ids:
        try:
            await config.bot.send_message(chat_id=chat_id, text=text[:3900])
        except Exception:
            logger.exception("Failed to send bot error notification to admin chat %s", chat_id)


async def on_aiogram_error(event: ErrorEvent) -> bool:
    exc = event.exception
    logger.exception("Cause exception while process update", exc_info=(type(exc), exc, exc.__traceback__))
    await notify_admins_about_error(event)
    return True


async def start():
    logger.info("Запуск бота...")

    dp = Dispatcher()
    dp.errors.register(on_aiogram_error)

    logger.info("Подключаемся к БД...")
    await config.connect_db()
    userDB = UsersDB(config.CONNECTION_DATABASE)
    await userDB.init()
    cargoDB = CargoService(conn=config.CONNECTION_DATABASE)
    await cargoDB.init()
    logger.info("База данных готова.")

    for router in get_routers():
        dp.include_router(router)
    logger.info("Роутеры подключены.")

    await config.bot.delete_webhook(drop_pending_updates=True)
    logger.info("Удалили вебхук. Бот переходит в polling режим.")

    outbox_poller = SiteOutboxPoller(
        bot=config.bot,
        site_api_url=config.SITE_API_URL,
        integration_secret=config.SITE_INTEGRATION_SECRET,
        admin_chat_id=config.ADMIN_CHAT_ID,
        poll_seconds=config.SITE_OUTBOX_POLL_SECONDS,
        enabled=config.SITE_OUTBOX_ENABLED,
    )
    outbox_task = asyncio.create_task(outbox_poller.run())

    logger.info("Бот запущен и ждёт события...")
    try:
        await dp.start_polling(config.bot)
    finally:
        outbox_task.cancel()
        await asyncio.gather(outbox_task, return_exceptions=True)
        await config.close_db()
        await config.bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(start())
    except KeyboardInterrupt:
        logger.warning("Остановлено пользователем (CTRL+C)")
    except Exception as e:
        logger.exception("Критическая ошибка при запуске бота: %s", e)
