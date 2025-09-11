import asyncio
import asyncpg
import logging
from aiogram import Dispatcher
import config
from app.routers import get_routers
from database import UsersDB, CargoService

# Настройка логов
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger(__name__)

async def start():
    logger.info("🚀 Запуск бота...")

    dp = Dispatcher()

    logger.info("🔌 Подключаемся к БД...")
    await config.connect_db()
    userDB = UsersDB(config.CONNECTION_DATABASE)
    await userDB.init()
    cargoDB = CargoService(conn=config.CONNECTION_DATABASE)
    await cargoDB.init()
    logger.info("✅ База данных готова.")

    for router in get_routers():
        dp.include_router(router)
    logger.info("✅ Роутеры подключены.")

    await config.bot.delete_webhook(drop_pending_updates=True)
    logger.info("📡 Удалили вебхук. Бот переходит в polling режим.")

    logger.info("🤖 Бот запущен и ждёт события...")
    await dp.start_polling(config.bot)


if __name__ == "__main__":
    try:
        asyncio.run(start())
    except KeyboardInterrupt:
        logger.warning("⛔ Остановлено пользователем (CTRL+C)")
    except Exception as e:
        logger.exception(f"💥 Критическая ошибка при запуске бота: {e}")
