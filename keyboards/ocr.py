from aiogram.filters.callback_data import CallbackData
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup
from .callback_data import OCREditFieldCallback, OCRFlowCallback, OCRTypeCallback, OCRPersonalCargoCallback, OCRScopeCallback, ProfileFlowCallback



class OCRKB:
    @staticmethod
    def edit_menu() -> InlineKeyboardMarkup:
        b = InlineKeyboardBuilder()
        b.button(text="💰 Цена", callback_data=OCREditFieldCallback(field="price").pack())
        b.button(text="🔢 Кол-во", callback_data=OCREditFieldCallback(field="quantity").pack())
        b.button(text="🎨 Цвет", callback_data=OCREditFieldCallback(field="color").pack())
        b.button(text="📏 Размер", callback_data=OCREditFieldCallback(field="size").pack())
        # b.button(text="🏷 Наименование", callback_data=OCREditFieldCallback(field="title").pack())
        b.button(text="➡️ Далее", callback_data=OCRFlowCallback(action="next_to_instruction").pack())
        b.adjust(2, 2, 1, 1)
        return b.as_markup()

    @staticmethod
    def back_to_edit(back="back_to_edit") -> InlineKeyboardMarkup:
        b = InlineKeyboardBuilder()
        b.button(text="⬅ Назад", callback_data=OCRFlowCallback(action=f"{back}").pack())
        return b.as_markup()

    @staticmethod
    def instruction(url: str) -> InlineKeyboardMarkup:
        b = InlineKeyboardBuilder()
        b.button(text="📘 Инструкция: где взять фото товара", url=url)
        b.button(text="⬅ Назад", callback_data=OCRFlowCallback(action="back_to_edit").pack())
        return b.as_markup()

    @staticmethod
    def final_actions() -> InlineKeyboardMarkup:
        b = InlineKeyboardBuilder()
        b.button(text="➕ Добавить", callback_data=OCRFlowCallback(action="confirm_final").pack())
        b.button(text="⬅ Назад", callback_data=OCRFlowCallback(action="back_after_scope").pack())
        b.adjust(2)
        return b.as_markup()

    @staticmethod
    def confirm_cancel() -> InlineKeyboardMarkup:
        b = InlineKeyboardBuilder()
        b.button(text="✅ Да, отменить", callback_data=OCRFlowCallback(action="confirm_cancel_yes").pack())
        b.button(text="↩️ Нет, вернуться", callback_data=OCRFlowCallback(action="confirm_cancel_no").pack())
        b.adjust(2)
        return b.as_markup()

    @staticmethod
    def type_menu() -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        builder.button(text="🧥 Одежда", callback_data=OCRTypeCallback(code="clothes").pack())
        builder.button(text="👟 Обувь", callback_data=OCRTypeCallback(code="shoes").pack())
        builder.button(text="🧼 Хозтовары", callback_data=OCRTypeCallback(code="household").pack())
        builder.button(text="⬅ Назад", callback_data=OCRFlowCallback(action="back_after_type").pack())
        builder.adjust(1, 1, 1, 1)
        return builder.as_markup()

    @staticmethod
    def scope_menu() -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        builder.button(text="🤝 Общая посылка", callback_data=OCRScopeCallback(scope="shared").pack())
        builder.button(text="👤 Личная посылка", callback_data=OCRScopeCallback(scope="personal").pack())
        builder.button(text="⬅ Назад", callback_data=OCRFlowCallback(action="back_after_scope").pack())
        builder.adjust(1, 1, 1)
        return builder.as_markup()

    @staticmethod
    def personal_cargos(cargos: list[dict]) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        if cargos:
            for c in cargos:
                title = c.get("title") or f"Посылка #{c['id']}"
                builder.button(text=f"📦 {title}", callback_data=OCRPersonalCargoCallback(cargo_id=c["id"]).pack())
        else:
            builder.button(text="👤 Профиль", callback_data=ProfileFlowCallback(action="profile").pack())


        builder.button(text="⬅ Назад", callback_data=OCRFlowCallback(action="back_after_scope").pack())
        builder.adjust(1)
        return builder.as_markup()
    

    @staticmethod
    def mismatch_upgrade() -> InlineKeyboardMarkup:
        b = InlineKeyboardBuilder()
        b.button(text="🔼 Продолжить и изменить тариф", callback_data=OCRFlowCallback(action="confirm_upgrade").pack())
        b.button(text="❌ Отмена", callback_data=OCRFlowCallback(action="cancel_mismatch").pack())
        b.adjust(1, 1)
        return b.as_markup()

    @staticmethod
    def mismatch_cheaper() -> InlineKeyboardMarkup:
        b = InlineKeyboardBuilder()
        b.button(text="➕ Добавить (понимаю риски)", callback_data=OCRFlowCallback(action="confirm_add_cheaper").pack())
        b.button(text="❌ Отмена", callback_data=OCRFlowCallback(action="cancel_mismatch").pack())
        b.adjust(1, 1)
        return b.as_markup()
