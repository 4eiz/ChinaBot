from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup
from .callback_data import AdminFlowCallback, MenuCallback, ProfileFlowCallback  # MenuCallback уже есть у тебя



class StartKB:
    @staticmethod
    def main(*, is_admin: bool = False) -> InlineKeyboardMarkup:
        b = InlineKeyboardBuilder()
        b.button(text="ℹ️ Информация", callback_data=MenuCallback(action="start_info").pack())
        b.button(text="🆘 Поддержка",  callback_data=MenuCallback(action="start_support").pack())
        b.button(text="👤 Профиль",    callback_data=ProfileFlowCallback(action="profile").pack())
        if is_admin:
            b.button(text="🛠 Админ-панель", callback_data=AdminFlowCallback(action="menu").pack())
        b.adjust(2, 1, 1 if is_admin else 0)
        return b.as_markup()

    @staticmethod
    def back_home() -> InlineKeyboardMarkup:
        b = InlineKeyboardBuilder()
        b.button(text="⬅ На главную", callback_data=MenuCallback(action="start_home").pack())
        b.adjust(1)
        return b.as_markup()
