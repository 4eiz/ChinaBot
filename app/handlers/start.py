from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.filters import CommandStart
from aiogram.utils.keyboard import InlineKeyboardBuilder
import aiohttp

from database import UsersDB, RequestsDB, CargoService
from app.handlers.form.fsm import FormState
from app.handlers import FormClientHandler
from app.utils import safe_delete
import config

from keyboards import StartKB, MenuCallback
from media import PhotoBank


class StartHandler:
    def __init__(self):
        self.users = UsersDB(config.CONNECTION_DATABASE)
        self.cargo_service = CargoService(conn=config.CONNECTION_DATABASE)
        self.router = Router()
        self.router.message.register(self.start, CommandStart())
        self.router.callback_query.register(self.confirm_site_login, F.data.startswith("site_login_confirm:"))
        self.router.callback_query.register(self.cancel_site_login, F.data.startswith("site_login_cancel:"))
        self.router.callback_query.register(self.start_info,    MenuCallback.filter(F.action == "start_info"))
        self.router.callback_query.register(self.start_support, MenuCallback.filter(F.action == "start_support"))
        self.router.callback_query.register(self.start_home,    MenuCallback.filter(F.action == "start_home"))

    @staticmethod
    def _referrer_from_start(text: str | None) -> int | None:
        if not text or " " not in text:
            return None
        payload = text.split(maxsplit=1)[1].strip()
        for prefix in ("ref_", "ref-", "ref"):
            if payload.startswith(prefix):
                payload = payload[len(prefix):]
                break
        try:
            referrer_id = int(payload)
        except (TypeError, ValueError):
            return None
        return referrer_id if referrer_id > 0 else None

    @staticmethod
    def _login_token_from_start(text: str | None) -> str | None:
        if not text or " " not in text:
            return None
        payload = text.split(maxsplit=1)[1].strip()
        for prefix in ("login_", "login-"):
            if payload.startswith(prefix):
                token = payload[len(prefix):].strip()
                return token or None
        return None

    @staticmethod
    def _site_login_keyboard(token: str):
        builder = InlineKeyboardBuilder()
        builder.button(text="✅ Подтвердить вход", callback_data=f"site_login_confirm:{token}")
        builder.button(text="❌ Отмена", callback_data=f"site_login_cancel:{token}")
        builder.adjust(1)
        return builder.as_markup()

    async def _approve_site_login(self, token: str, user):
        site_api_url = (config.SITE_API_URL or "").rstrip("/")
        if not site_api_url:
            raise RuntimeError("SITE_API_URL is not configured")

        payload = {
            "token": token,
            "telegram_id": user.id,
            "name": user.first_name or "",
            "surname": user.last_name or "",
        }
        headers = {"X-Telegram-Bot-Token": config.SITE_BOT_TOKEN or ""}
        timeout = aiohttp.ClientTimeout(total=12)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                f"{site_api_url}/api/profile/auth/telegram/approve/",
                json=payload,
                headers=headers,
            ) as resp:
                if resp.status not in (200, 201):
                    text = await resp.text()
                    raise RuntimeError(f"Site login approve failed: {resp.status} {text}")
                return await resp.json()

    async def start(self, message: Message, state: FSMContext):
        await safe_delete(message)

        login_token = self._login_token_from_start(message.text)
        if login_token:
            await message.answer(
                "🔐 <b>Вход в личный кабинет</b>\n\n"
                "Нажмите кнопку ниже, чтобы подтвердить вход на сайте.",
                reply_markup=self._site_login_keyboard(login_token),
            )
            return

        user_id = message.from_user.id
        referrer_id = self._referrer_from_start(message.text)
        user = await self.users.get_user(user_id=user_id)
        is_admin = bool(user and user.get("is_admin"))

        if user is None:
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
            if referrer_id and referrer_id != user_id:
                await state.update_data(referrer_id=referrer_id)
            form = FormClientHandler(conn=config.CONNECTION_DATABASE)
            photo = PhotoBank.get_file('SLIDE1')
            await message.answer_photo(photo=photo, caption=form.text_name)
            return

        if referrer_id and referrer_id != user_id:
            created = await self.users.create_referral_relationship(
                referrer_id=referrer_id,
                invited_id=user_id,
                source="bot_link",
                note="created from /start referral link",
            )
            if created:
                try:
                    await self.cargo_service.recalculate_referrals(user_id=user_id)
                except Exception as exc:
                    print(f"Failed to recalculate referrals for user {user_id}: {exc}")

        text = (
            f"👋 <b>Добро пожаловать в {config.SHOP_NAME}!</b>\n\n"
            "Здесь вы можете оформить товары из Китая, вести посылки и отслеживать оплату.\n"
            "Выберите раздел ниже:"
        )
        kb = StartKB.main(is_admin=is_admin)
        photo = PhotoBank.get_file('MENU_IMAGE')
        await message.answer_photo(photo=photo, caption=text, reply_markup=kb)

    async def confirm_site_login(self, call: CallbackQuery):
        await call.answer()
        token = (call.data or "").split(":", maxsplit=1)[1]
        try:
            await self._approve_site_login(token, call.from_user)
        except Exception as exc:
            print(f"Failed to approve site login for {call.from_user.id}: {exc}")
            await call.answer("Не удалось подтвердить вход", show_alert=True)
            await call.message.edit_text(
                "Не удалось подтвердить вход. Вернитесь на сайт и попробуйте начать вход заново."
            )
            return

        await call.answer("Вход подтвержден")
        await call.message.edit_text(
            "✅ Вход подтвержден. Вернитесь на сайт, кабинет откроется автоматически."
        )

    async def cancel_site_login(self, call: CallbackQuery):
        await call.answer("Вход отменен")
        await call.message.edit_text("Вход отменен. На сайте можно начать новую попытку.")

    async def start_info(self, call: CallbackQuery, callback_data: MenuCallback):
        await call.answer()
        await safe_delete(call.message)

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
        photo = PhotoBank.get_file('INFO_IMAGE')
        await call.message.answer_photo(
            photo=photo, caption=text, reply_markup=kb,
            disable_web_page_preview=True,
        )

    async def start_support(self, call: CallbackQuery, callback_data: MenuCallback):
        await call.answer()
        await safe_delete(call.message)

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
        photo = PhotoBank.get_file('SUPPORT_IMAGE')
        await call.message.answer_photo(photo=photo, caption=text, reply_markup=kb)

    async def start_home(self, call: CallbackQuery, callback_data: MenuCallback):
        await call.answer()
        await safe_delete(call.message)

        user = await self.users.get_user(user_id=call.from_user.id)
        is_admin = bool(user and user.get("is_admin"))

        text = (
            f"👋 <b>Добро пожаловать в {config.SHOP_NAME}!</b>\n\n"
            "Выберите раздел ниже:"
        )
        kb = StartKB.main(is_admin=is_admin)
        photo = PhotoBank.get_file('MENU_IMAGE')
        await call.message.answer_photo(photo=photo, caption=text, reply_markup=kb)
