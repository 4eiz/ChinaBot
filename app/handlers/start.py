from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.filters import CommandStart

from database import UsersDB, RequestsDB
from app.handlers.form.fsm import FormState
from app.handlers import FormClientHandler
from media import PhotoBank
import config

from keyboards import StartKB, MenuCallback
from media import PhotoBank


class StartHandler:
    def __init__(self):
        self.users = UsersDB(config.CONNECTION_DATABASE)
        self.router = Router()
        # /start
        self.router.message.register(self.start, CommandStart())
        # callbacks
        self.router.callback_query.register(self.start_info, MenuCallback.filter(F.action == "start_info"))
        self.router.callback_query.register(self.start_support, MenuCallback.filter(F.action == "start_support"))
        self.router.callback_query.register(self.start_home, MenuCallback.filter(F.action == "start_home"))


    async def start(self, message: Message, state: FSMContext):
        await message.delete()

        user_id = message.from_user.id
        user = await self.users.get_user(user_id=user_id)
        is_admin = bool(user and user.get("is_admin"))

        if user is None:
            # новичок — анкета
            req_db = RequestsDB(conn=config.CONNECTION_DATABASE)
            await req_db.init()
            if await req_db.has_active_request(user_id):
                status = await req_db.get_last_request_status(user_id)
                text = (
                    f"⏳ У вас уже есть заявка со статусом: <b>{status}</b>.\n"
                    f"Пожалуйста, дождитесь решения."
                )
                await message.answer(text=text, parse_mode="HTML")
                return

            await state.set_state(FormState.name)
            form = FormClientHandler(conn=config.CONNECTION_DATABASE)
            photo = PhotoBank.get_file('SLIDE1')
            await message.answer_photo(
                photo=photo,
                caption=form.text_name
            )
            return

        # старый пользователь — показываем домашнее меню
        text = (
            f"👋 <b>Добро пожаловать в {config.SHOP_NAME}!</b>\n\n"
            "Здесь вы можете оформить товары из Китая, вести посылки и отслеживать оплату.\n"
            "Выберите раздел ниже:"
        )
        kb = StartKB.main(is_admin=is_admin)
        photo = PhotoBank.get_file('MENU_IMAGE')

        await message.answer_photo(photo=photo, caption=text, reply_markup=kb)

    # --- callbacks ---

    async def start_info(self, call: CallbackQuery, callback_data: MenuCallback):
        await call.answer()
        await call.message.delete()

        text = (
            "ℹ️ <b>Полезная информация</b>\n\n"
            f"📣 <b>Наш канал:</b> <a href=\"{config.CHANNEL_LINK}\">перейти</a>\n"
            f"📘 <b>Инструкция по использованию:</b> <a href=\"{config.GUIDE_LINK}\">читать</a>\n\n"
            "Что здесь можно:\n"
            "• Создавать посылки и добавлять товары 🛒\n"
            "• Отправлять заявку на отправку посылки ✉️\n"
            "• Смотреть сводку оплат и статусы доставки 📦\n\n"
            "Подсказка: в профиле доступны ваши посылки и настройки."
        )
        kb = StartKB.back_home()

        await call.message.answer(text=text, reply_markup=kb, disable_web_page_preview=True)


    async def start_support(self, call: CallbackQuery, callback_data: MenuCallback):
        await call.answer()
        await call.message.delete()

        text = (
            "🆘 <b>Поддержка</b>\n\n"
            f"💬 Telegram: {config.SUPPORT_TG}\n"
            f"✉️ Email: <code>{config.SUPPORT_EMAIL}</code>\n"
            f"🕒 Время ответа: {config.SUPPORT_HOURS}\n\n"
            "Пожалуйста, опишите проблему максимально подробно:\n"
            "• Номер посылки (если есть)\n"
            "• Ссылки на товары / скриншоты\n"
            "• Что ожидали и что произошло\n\n"
            "Мы обязательно поможем!"
        )
        kb = StartKB.back_home()

        await call.message.answer(text=text, reply_markup=kb)

    async def start_home(self, call: CallbackQuery, callback_data: MenuCallback):
        await call.answer()
        await call.message.delete()


        user = await self.users.get_user(user_id=call.from_user.id)
        is_admin = bool(user and user.get("is_admin"))

        text = (
            f"👋 <b>Добро пожаловать в {config.SHOP_NAME}!</b>\n\n"
            "Выберите раздел ниже:"
        )
        kb = StartKB.main(is_admin=is_admin)
        photo = PhotoBank.get_file('MENU_IMAGE')

        await call.message.answer_photo(photo=photo, caption=text, reply_markup=kb)