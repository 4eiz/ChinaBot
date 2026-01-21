from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command
from keyboards import ProfileKB, ProfileFlowCallback
from database import UsersDB
from database.orders import CargoService
from decimal import Decimal

from media import PhotoBank


class ProfileHandler:
    """Хендлер профиля пользователя."""

    def __init__(self, conn):
        self.router = Router()

        self.users_db = UsersDB(conn=conn)
        self.cargo_service = CargoService(conn=conn)

        # регистрируем хендлеры
        self.router.message.register(self.profile, Command("profile"))
        self.router.callback_query.register(self.open_profile, ProfileFlowCallback.filter(F.action.in_(["profile", "open", "back_to_profile"])))
        self.router.callback_query.register(self.back, ProfileFlowCallback.filter(F.action == "back"))

    async def _render_profile(self, user_id: int) -> str:
        user = await self.users_db.get_user(user_id=user_id)
        if not user:
            return "❌ Пользователь не найден."

        balance_yuan = Decimal(str(user.get("balance") or 0))
        course = Decimal(str(user.get("rate") or 0.1822))
        balance_usd = (balance_yuan * course).quantize(Decimal("0.01"))

        parcels_count = await self.cargo_service.cargos.count_by_user(user_id=user_id)
        spent_total_yuan = await self.cargo_service.items.total_spent_by_user(user_id=user_id)
        spent_total_usd = (spent_total_yuan * course).quantize(Decimal("0.01"))


        text = (
            f"👤 <b>ID:</b> <code>{user_id}</code>\n"
            f"💳 <b>Баланс:</b> <code>{balance_usd}$</code>\n"
            f"💱 <b>Курс:</b> <code>{course}</code>\n"
            f"📦 <b>Посылок:</b> <code>{parcels_count}</code>\n"
            f"📊 <b>Потрачено:</b> <code>{spent_total_usd}$</code>"
        )
        return text

    async def profile(self, message: types.Message, state: FSMContext):
        if state:
            await state.clear()

        await message.delete()

        text = await self._render_profile(user_id=message.from_user.id)
        is_admin = bool(await self.users_db.is_admin(user_id=message.from_user.id))
        kb = ProfileKB.main_menu(is_admin=is_admin)

        photo = PhotoBank.get_file('PROFILE_IMAGE')

        await message.answer_photo(photo=photo, caption=text, reply_markup=kb)

    async def open_profile(self, call: types.CallbackQuery, state: FSMContext):
        if state:
            await state.clear()

        await call.message.delete()

        text = await self._render_profile(user_id=call.from_user.id)
        is_admin = bool(await self.users_db.is_admin(user_id=call.from_user.id))
        kb = ProfileKB.main_menu(is_admin=is_admin)
        photo = PhotoBank.get_file('PROFILE_IMAGE')

        await call.message.answer_photo(photo=photo, caption=text, reply_markup=kb)

    async def back(self, call: types.CallbackQuery):
        await call.message.delete()
        await call.message.answer("⬅ Вы вернулись в меню.")  # тут подставишь своё главное меню

