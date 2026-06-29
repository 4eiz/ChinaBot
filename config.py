import json
import os
from decimal import Decimal
from pathlib import Path

import asyncpg
from aiogram import Bot
from aiogram.client.bot import DefaultBotProperties
from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / '.env')
BOT_TOKEN = os.getenv('BOT_TOKEN')
BOT_USERNAME = os.getenv('BOT_USERNAME', '')
SHOP_NAME = os.getenv('SHOP_NAME')


# БАЗА ДАННЫХ
DB_NAME = os.getenv('DB_NAME')
DB_PASSWORD = os.getenv('DB_PASSWORD')
DB_IP = os.getenv('DB_IP')
DB_PORT = os.getenv('DB_PORT')
DB_NAME_DATABASE = os.getenv('DB_NAME_DATABASE')
DSN = f"postgresql://{DB_NAME}:{DB_PASSWORD}@{DB_IP}:{DB_PORT}/{DB_NAME_DATABASE}"


async def _setup_connection(conn: asyncpg.Connection) -> None:
    await conn.set_type_codec(
        'json',
        encoder=json.dumps,
        decoder=json.loads,
        schema='pg_catalog',
    )
    await conn.set_type_codec(
        'jsonb',
        encoder=json.dumps,
        decoder=json.loads,
        schema='pg_catalog',
    )


class DatabasePoolAdapter:
    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    async def execute(self, *args, **kwargs):
        async with self._pool.acquire() as conn:
            return await conn.execute(*args, **kwargs)

    async def fetch(self, *args, **kwargs):
        async with self._pool.acquire() as conn:
            return await conn.fetch(*args, **kwargs)

    async def fetchrow(self, *args, **kwargs):
        async with self._pool.acquire() as conn:
            return await conn.fetchrow(*args, **kwargs)

    async def fetchval(self, *args, **kwargs):
        async with self._pool.acquire() as conn:
            return await conn.fetchval(*args, **kwargs)

    def transaction(self):
        return _PoolTransaction(self._pool)

    async def close(self) -> None:
        await self._pool.close()


class _PoolTransaction:
    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool
        self._connection = None
        self._transaction = None

    async def __aenter__(self):
        self._connection = await self._pool.acquire()
        self._transaction = self._connection.transaction()
        await self._transaction.__aenter__()
        return self._connection

    async def __aexit__(self, exc_type, exc, tb):
        try:
            return await self._transaction.__aexit__(exc_type, exc, tb)
        finally:
            await self._pool.release(self._connection)


CONNECTION_DATABASE: DatabasePoolAdapter | None = None


async def connect_db():
    global CONNECTION_DATABASE
    pool = await asyncpg.create_pool(
        dsn=DSN,
        min_size=int(os.getenv('DB_POOL_MIN_SIZE', '1') or '1'),
        max_size=int(os.getenv('DB_POOL_MAX_SIZE', '10') or '10'),
        init=_setup_connection,
    )
    CONNECTION_DATABASE = DatabasePoolAdapter(pool)


async def close_db():
    if CONNECTION_DATABASE is not None:
        await CONNECTION_DATABASE.close()


# АДМИН
ADMIN_ID = os.getenv('ADMIN_ID')
ADMIN_NUMBER = os.getenv('ADMIN_NUMBER')
ADMIN_FORM_CHAT_ID = os.getenv('ADMIN_FORM_CHAT_ID')
ADMIN_CHAT_ID = os.getenv('ADMIN_CHAT_ID')


# НАСТРОЙКА АПИ
SITE_API_URL = os.getenv('SITE_API_URL', 'http://127.0.0.1:8028')
SITE_INTEGRATION_SECRET = os.getenv('SITE_INTEGRATION_SECRET', '')
SITE_OUTBOX_ENABLED = os.getenv('SITE_OUTBOX_ENABLED', '1').strip().lower() not in {'0', 'false', 'no', 'off'}
SITE_OUTBOX_POLL_SECONDS = int(os.getenv('SITE_OUTBOX_POLL_SECONDS', '10') or '10')
PRODUCT_RECOGNITION_BASE_URL = os.getenv('PRODUCT_RECOGNITION_BASE_URL', 'https://sub2api.robcargo.my/v1')
PRODUCT_RECOGNITION_API_KEY = os.getenv('PRODUCT_RECOGNITION_API_KEY', '')
PRODUCT_RECOGNITION_MODEL = os.getenv('PRODUCT_RECOGNITION_MODEL', 'gemini-2.5-flash')
PRODUCT_RECOGNITION_API_MODE = os.getenv('PRODUCT_RECOGNITION_API_MODE', 'antigravity')
PRODUCT_RECOGNITION_TIMEOUT_SECONDS = int(os.getenv('PRODUCT_RECOGNITION_TIMEOUT_SECONDS', '45') or '45')


CHANNEL_LINK = os.getenv("CHANNEL_LINK", "https://t.me/your_channel")
GUIDE_LINK = os.getenv("GUIDE_LINK", "https://t.me/your_guide_post")
SUPPORT_TG = os.getenv("SUPPORT_TG", "@your_support_username")
SUPPORT_EMAIL = os.getenv("SUPPORT_EMAIL", "support@example.com")
SUPPORT_HOURS = os.getenv("SUPPORT_HOURS", "Пн–Пт 10:00–19:00 (Мск)")


CLEAR_RATE = Decimal(os.getenv('CLEAR_RATE', '0') or '0')
DEFAULT_RATE = Decimal(os.getenv('DEFAULT_RATE', '0.1898') or '0.1898')

# Курс USD → BYN для экспорта ТК Экспедиция (1 USD = 2.9 BYN по умолчанию)
USD_TO_BYN = Decimal(os.getenv('USD_TO_BYN', '2.9') or '2.9')


bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode='HTML'))
