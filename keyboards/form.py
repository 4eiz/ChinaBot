from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

from keyboards.callback_data import SourceCallback, FormBackCallback, ConfirmCallback, RequestActionCallback


class FormKB:
    # можно использовать и как класс-перечисление, и для генерации кнопок
    SOURCES = {
        "Реклама": "ads",
        "Друзья": "friends",
        "Гугл": "google",
        "Другое": "other"
    }

    @classmethod
    def source_keyboard(cls) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()

        for text, value in cls.SOURCES.items():
            builder.button(
                text=text,
                callback_data=SourceCallback(value=value).pack()
            )

        builder.button(
            text="⬅ Назад",
            callback_data=FormBackCallback(step="phone").pack()
        )

        builder.adjust(2, 2)
        return builder.as_markup()


    @staticmethod
    def finish_keyboard(to_step) -> InlineKeyboardMarkup:
        """
        Финишная клавиатура для подтверждения отправки заявки
        """

        builder = InlineKeyboardBuilder()

        builder.button(text="✅ Отправить", callback_data=ConfirmCallback(action='yes'))
        builder.button(text="⬅ Назад", callback_data=FormBackCallback(step=to_step))

        return builder.as_markup()


    @staticmethod
    def back_keyboard(to_step: str) -> InlineKeyboardMarkup:
        """
        Клавиатура только с кнопкой 'Назад'
        """
        builder = InlineKeyboardBuilder()
        builder.button(
            text="⬅ Назад",
            callback_data=FormBackCallback(step=to_step).pack()
        )
        return builder.as_markup()

    @staticmethod
    def contact_keyboard() -> ReplyKeyboardMarkup:
        return ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="📱 Отправить номер", request_contact=True)]
            ],
            resize_keyboard=True,
            one_time_keyboard=True,
            input_field_placeholder="Нажмите, чтобы поделиться номером"
        )
    

class RequestsKB:
    @staticmethod
    def decision_keyboard(request_id: int) -> InlineKeyboardMarkup:
        b = InlineKeyboardBuilder()
        b.button(text="✅ Принять", callback_data=RequestActionCallback(action="approve", request_id=request_id).pack())
        b.button(text="❌ Отклонить", callback_data=RequestActionCallback(action="reject", request_id=request_id).pack())
        b.adjust(2)
        return b.as_markup()