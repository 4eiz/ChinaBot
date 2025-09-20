import os
import asyncpg
import json
from decimal import Decimal
from aiogram import Bot
from aiogram.client.bot import DefaultBotProperties
from dotenv import load_dotenv



load_dotenv()
BOT_TOKEN = os.getenv('BOT_TOKEN')
SHOP_NAME = os.getenv('SHOP_NAME')


# БАЗА ДАННЫХ
DB_NAME = os.getenv('DB_NAME')
DB_PASSWORD = os.getenv('DB_PASSWORD')
DB_IP = os.getenv('DB_IP')
DB_PORT = os.getenv('DB_PORT')
DB_NAME_DATABASE = os.getenv('DB_NAME_DATABASE')
DSN = f"postgresql://{DB_NAME}:{DB_PASSWORD}@{DB_IP}:{DB_PORT}/{DB_NAME_DATABASE}"


CONNECTION_DATABASE: asyncpg.Connection = None
async def connect_db():
    global CONNECTION_DATABASE
    conn = await asyncpg.connect(DSN)

    # ВКЛЮЧАЕМ авто-кодек для json / jsonb
    await conn.set_type_codec(
        'json',
        encoder=json.dumps,
        decoder=json.loads,
        schema='pg_catalog'
    )
    await conn.set_type_codec(
        'jsonb',
        encoder=json.dumps,
        decoder=json.loads,
        schema='pg_catalog'
    )

    CONNECTION_DATABASE = conn


# АДМИН
ADMIN_ID = os.getenv('ADMIN_ID')
ADMIN_NUMBER = os.getenv('ADMIN_NUMBER')
ADMIN_FORM_CHAT_ID = os.getenv('ADMIN_FORM_CHAT_ID')
ADMIN_CHAT_ID = os.getenv('ADMIN_CHAT_ID')


# НАСТРОЙКА АПИ
API_URL = os.getenv('API_URL')
API_USERNAME = os.getenv('API_USERNAME')
API_PASSWORD = os.getenv('API_PASSWORD')


# ССЫЛКИ
INSTRUCTION_URL1 = os.getenv('INSTRUCTION_URL1')
CHANNEL_LINK = os.getenv("CHANNEL_LINK", "https://t.me/your_channel")
GUIDE_LINK = os.getenv("GUIDE_LINK", "https://t.me/your_guide_post")
SUPPORT_TG = os.getenv("SUPPORT_TG", "@your_support_username")
SUPPORT_EMAIL = os.getenv("SUPPORT_EMAIL", "support@example.com")
SUPPORT_HOURS = os.getenv("SUPPORT_HOURS", "Пн–Пт 10:00–19:00 (Мск)")




CLEAR_RATE = Decimal(os.getenv('CLEAR_RATE', '0') or '0')


bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode='HTML'))