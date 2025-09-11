# keyboards/admin_kb.py  (или где у тебя лежит AdminKB)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup
from .callback_data import AdminFlowCallback, PaymentFlowCallback

class AdminKB:
    @staticmethod
    def menu() -> InlineKeyboardMarkup:
        b = InlineKeyboardBuilder()
        b.button(text="📦 Посылки", callback_data=AdminFlowCallback(action="shipments").pack())
        b.button(text="👥 Пользователи (скоро)", callback_data=AdminFlowCallback(action="users_stub").pack())
        b.adjust(1, 1)
        return b.as_markup()

    @staticmethod
    def shipments_list(cargos: list[dict]) -> InlineKeyboardMarkup:
        b = InlineKeyboardBuilder()
        for c in cargos or []:
            title = c.get("title") or f"#{c['id']}"
            b.button(
                text=f"📦 #{c['id']} | {title}",
                callback_data=AdminFlowCallback(action="open", id=c["id"]).pack()
            )
        b.button(text="⬅ Назад", callback_data=AdminFlowCallback(action="menu").pack())
        b.adjust(1)
        return b.as_markup()

    @staticmethod
    def shipment_view(cargo_id: int) -> InlineKeyboardMarkup:
        b = InlineKeyboardBuilder()
        b.button(text="🔖 Статусы", callback_data=AdminFlowCallback(action="status", id=cargo_id).pack())
        b.button(text="👥 Сводка по людям", callback_data=AdminFlowCallback(action="summary", id=cargo_id).pack())
        b.button(text="📄 Экспорт PDF (админ)", callback_data=AdminFlowCallback(action="export_admin_pdf", id=cargo_id).pack())
        b.button(text="🧾 Экспорт товаров (PDF)", callback_data=AdminFlowCallback(action="export_items_pdf", id=cargo_id).pack())
        b.button(text="⬅ Назад", callback_data=AdminFlowCallback(action="shipments").pack())
        b.adjust(1)
        return b.as_markup()

    @staticmethod
    def summary_menu(cargo_id: int, users: list[int]) -> InlineKeyboardMarkup:
        b = InlineKeyboardBuilder()
        for uid in users:
            b.button(
                text=f"💵 Внести платёж для {uid}",
                callback_data=AdminFlowCallback(action="add_payment", id=cargo_id, user_id=uid).pack()
            )
        b.button(text="⬅ Назад", callback_data=AdminFlowCallback(action="open", id=cargo_id).pack())
        b.adjust(1)
        return b.as_markup()
    
    @staticmethod
    def payment_kind(cargo_id: int) -> InlineKeyboardMarkup:
        """
        Шаг 1: выбор типа платежа кнопками.
        """
        b = InlineKeyboardBuilder()
        # кодируем выбор в action, чтобы не трогать схему callback_data
        b.button(text="🛍 Товар ($)", callback_data=AdminFlowCallback(action="payment", status="goods_usd").pack())
        b.button(text="🚚 CN→MSK ($)", callback_data=AdminFlowCallback(action="payment", status="delivery_msk").pack())
        b.button(text="🚛 MSK→BY ($)", callback_data=AdminFlowCallback(action="payment", status="delivery_by").pack())
        b.button(text="💳 Аванс ($)", callback_data=AdminFlowCallback(action="payment", status="advance").pack())
        b.button(text="🔁 Возврат ($)", callback_data=AdminFlowCallback(action="payment", status="refund").pack())
        b.button(text="🧩 Другое ($)", callback_data=AdminFlowCallback(action="payment", status="other").pack())
        b.button(text="⬅ Назад", callback_data=AdminFlowCallback(action="summary", id=cargo_id).pack())
        b.adjust(2, 2, 2, 1)
        return b.as_markup()

    @staticmethod
    def payment_amount() -> InlineKeyboardMarkup:
        b = InlineKeyboardBuilder()
        for amount in ("5","10","20","50","100","200"):
            b.button(text=f"{amount} $", callback_data=PaymentFlowCallback(action="pay_amount", amount=amount).pack())
        b.button(text="🔢 Другая сумма", callback_data=AdminFlowCallback(action="pay_amount_custom").pack())
        # Назад к типам (ВАЖНО для твоего первого бага)
        b.button(text="⬅ Назад к типам", callback_data=AdminFlowCallback(action="back").pack())
        b.adjust(3, 3, 1)
        return b.as_markup()

    @staticmethod
    def payment_note_choice() -> InlineKeyboardMarkup:
        b = InlineKeyboardBuilder()
        b.button(text="💾 Сохранить", callback_data=AdminFlowCallback(action="pay_save").pack())
        b.button(text="📝 Комментарий", callback_data=AdminFlowCallback(action="pay_add_note").pack())
        b.button(text="⬅ Назад к сумме", callback_data=AdminFlowCallback(action="back").pack())
        return b.as_markup()
    
    @staticmethod
    def payment_back() -> InlineKeyboardMarkup:
        b = InlineKeyboardBuilder()
        b.button(text="⬅️ Назад", callback_data=AdminFlowCallback(action="back").pack())
        # b.button(text="❌ Отмена", callback_data=AdminFlowCallback(action="payment_cancel", id=cargo_id).pack())
        b.adjust(2)
        return b.as_markup()


    @staticmethod
    def back_to_shipment(cargo_id: int) -> InlineKeyboardMarkup:
        b = InlineKeyboardBuilder()
        b.button(text="⬅ Назад к посылке", callback_data=AdminFlowCallback(action="open", id=cargo_id).pack())
        b.adjust(1)
        return b.as_markup()

    # 💡 ЕДИНАЯ клавиатура для всех шагов FSM
    @staticmethod
    def fsm_nav(cargo_id: int) -> InlineKeyboardMarkup:
        b = InlineKeyboardBuilder()
        b.button(text="⬅️ Назад", callback_data=AdminFlowCallback(action="back", id=cargo_id).pack())
        b.button(text="❌ Отмена", callback_data=AdminFlowCallback(action="payment_cancel", id=cargo_id).pack())
        b.adjust(2)
        return b.as_markup()

    @staticmethod
    def shipment_moderation(cargo_id: int) -> InlineKeyboardMarkup:
        """
        Кнопки модерации посылки в админ-чате.
        """
        b = InlineKeyboardBuilder()
        b.button(text="✅ Принять", callback_data=AdminFlowCallback(action="accept_send", id=cargo_id).pack())
        b.button(text="❌ Отклонить", callback_data=AdminFlowCallback(action="reject_send", id=cargo_id).pack())
        b.adjust(2)
        return b.as_markup()
    
    @staticmethod
    def status_picker(cargo_id: int):
        """
        Клавиатура для выбора статуса посылки админом.
        """
        b = InlineKeyboardBuilder()
        # Каждой кнопке - свой action (status_open, status_pending, ...)
        b.button(text="✏️ Редактируется", callback_data=AdminFlowCallback(action="set_status", status='open', id=cargo_id).pack())
        b.button(text="⏳ Ожидает решения", callback_data=AdminFlowCallback(action="set_status", status='pending', id=cargo_id).pack())
        b.button(text="✅ Принята (закрыта)", callback_data=AdminFlowCallback(action="set_status", status='closed', id=cargo_id).pack())
        b.button(text="❌ Отклонена", callback_data=AdminFlowCallback(action="set_status", status='rejected', id=cargo_id).pack())
        b.button(text="🗄 Архив", callback_data=AdminFlowCallback(action="set_status", status='archived', id=cargo_id).pack())
        b.button(text="⬅ Назад", callback_data=AdminFlowCallback(action="open", id=cargo_id).pack())
        b.adjust(1, 1, 1, 1, 1, 1)
        return b.as_markup()