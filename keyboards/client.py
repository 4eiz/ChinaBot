from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup
from .callback_data import MenuCallback, ProfileFlowCallback




class MenuKB:

    @staticmethod
    def main_menu(*, is_admin: bool = False) -> InlineKeyboardMarkup:
        b = InlineKeyboardBuilder()
        b.button(text="Профиль", callback_data=ProfileFlowCallback(action="profile").pack())
        if is_admin:
            b.button(text="🛠 Админ-панель", callback_data=ProfileFlowCallback(action="menu").pack())
        b.button(text="⬅ Назад", callback_data=ProfileFlowCallback(action="back").pack())
        b.adjust(1, 1, 1)
        return b.as_markup()