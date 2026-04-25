# keyboards/admin_kb.py  (или где у тебя лежит AdminKB)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup
from .callback_data import AdminFlowCallback, PaymentFlowCallback, ProfileFlowCallback, ShipmentFlowCallback

class AdminKB:
    @staticmethod
    def menu() -> InlineKeyboardMarkup:
        b = InlineKeyboardBuilder()
        b.button(text="📦 Посылки", callback_data=AdminFlowCallback(action="shipments").pack())
        b.button(text="👥 Пользователи (скоро)", callback_data=AdminFlowCallback(action="users_stub").pack())
        b.button(text="⬅ Назад", callback_data=ProfileFlowCallback(action="back_to_profile").pack())

        b.adjust(1, 1)
        return b.as_markup()

    @staticmethod
    def shipments_list(
        cargos: list[dict],
        *,
        tab: str = "shared",
        page: int = 1,
        total_pages: int = 1,
        has_prev: bool = False,
        has_next: bool = False,
    ) -> InlineKeyboardMarkup:
        b = InlineKeyboardBuilder()

        b.button(
            text=("👥 Общие ✅" if tab=="shared" else "👥 Общие"),
            callback_data=AdminFlowCallback(action="shipments", status="shared", id=1).pack()
        )
        b.button(
            text=("👤 Личные ✅" if tab=="personal" else "👤 Личные"),
            callback_data=AdminFlowCallback(action="shipments", status="personal", id=1).pack()
        )
        b.button(
            text=("🗄 Архив ✅" if tab=="archived" else "🗄 Архив"),
            callback_data=AdminFlowCallback(action="shipments", status="archived", id=1).pack()
        )

        for c in cargos or []:
            title = c.get("title") or f"#{c['id']}"
            b.button(
                text=title,
                callback_data=AdminFlowCallback(action="open", id=c["id"]).pack()
            )

        if total_pages > 1:
            if has_prev:
                b.button(
                    text="◀️",
                    callback_data=AdminFlowCallback(action="shipments", status=tab, id=page-1).pack()
                )
            b.button(
                text=f"{page}/{total_pages}",
                callback_data=AdminFlowCallback(action="shipments", status=tab, id=page).pack()
            )
            if has_next:
                b.button(
                    text="▶️",
                    callback_data=AdminFlowCallback(action="shipments", status=tab, id=page+1).pack()
                )

        b.button(text="⬅ Назад", callback_data=AdminFlowCallback(action="menu").pack())

        sizes: list[int] = [3]
        if cargos:
            sizes += [1] * len(cargos)
        if total_pages > 1:
            sizes.append(3 if (has_prev and has_next) else 2 if (has_prev or has_next) else 1)
        sizes.append(1)
        b.adjust(*sizes)
        return b.as_markup()


    @staticmethod
    def shipment_view(cargo: int) -> InlineKeyboardMarkup:
        cargo_id = cargo.get('id')

        b = InlineKeyboardBuilder()
        b.button(text="🔖 Статусы",              callback_data=AdminFlowCallback(action="status",              id=cargo_id).pack())
        b.button(text="👥 Сводка по людям",       callback_data=AdminFlowCallback(action="summary",             id=cargo_id).pack())
        # Excel-экспорты — группа из 3 кнопок
        b.button(text="📊 Excel 352",             callback_data=AdminFlowCallback(action="export_excel_352",         id=cargo_id).pack())
        b.button(text="📊 Excel Садовод",         callback_data=AdminFlowCallback(action="export_excel_sadovod",     id=cargo_id).pack())
        b.button(text="📬 ТК Экспедиция",         callback_data=AdminFlowCallback(action="export_excel_expedition",  id=cargo_id).pack())
        # PDF-экспорт
        b.button(text="🧾 Экспорт товаров (PDF)", callback_data=AdminFlowCallback(action="export_items_pdf",     id=cargo_id).pack())

        if cargo.get("status") == "open":
            b.button(
                text="📨 Отправить посылку",
                callback_data=ShipmentFlowCallback(action="send_request", id=cargo_id).pack()
            )

        b.button(text="⬅ Назад", callback_data=AdminFlowCallback(action="shipments").pack())

        # layout:
        # row 1: Статусы | Сводка (2)
        # row 2: Excel 352 | Excel Садовод | 📬 ТК Экспедиция (3)
        # row 3: Экспорт товаров PDF (1)
        # row 4 (опционально): Отправить посылку (1)
        # row last: Назад (1)
        sizes = [2, 3, 1]
        if cargo.get("status") == "open":
            sizes.append(1)
        sizes.append(1)
        b.adjust(*sizes)
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
        b = InlineKeyboardBuilder()
        b.button(text="🛍 Товар ($)",    callback_data=AdminFlowCallback(action="payment", status="goods_usd").pack())
        b.button(text="🚚 CN→MSK ($)",  callback_data=AdminFlowCallback(action="payment", status="delivery_msk").pack())
        b.button(text="🚛 MSK→BY ($)",  callback_data=AdminFlowCallback(action="payment", status="delivery_by").pack())
        b.button(text="💳 Аванс ($)",   callback_data=AdminFlowCallback(action="payment", status="advance").pack())
        b.button(text="🔁 Возврат ($)", callback_data=AdminFlowCallback(action="payment", status="refund").pack())
        b.button(text="🧩 Другое ($)",  callback_data=AdminFlowCallback(action="payment", status="other").pack())
        b.button(text="⬅ Назад",        callback_data=AdminFlowCallback(action="back", id=cargo_id).pack())
        b.adjust(2, 2, 2, 1)
        return b.as_markup()

    @staticmethod
    def payment_amount() -> InlineKeyboardMarkup:
        b = InlineKeyboardBuilder()
        for amount in ("5", "10", "20", "50", "100", "200"):
            b.button(text=f"{amount} $", callback_data=PaymentFlowCallback(action="pay_amount", amount=amount).pack())
        b.button(text="⬅ Назад к типам", callback_data=AdminFlowCallback(action="back").pack())
        b.adjust(3, 3, 1)
        return b.as_markup()

    @staticmethod
    def payment_note_choice() -> InlineKeyboardMarkup:
        b = InlineKeyboardBuilder()
        b.button(text="💾 Сохранить",      callback_data=AdminFlowCallback(action="pay_save").pack())
        b.button(text="📝 Комментарий",    callback_data=AdminFlowCallback(action="pay_add_note").pack())
        b.button(text="⬅ Назад к сумме",  callback_data=AdminFlowCallback(action="back").pack())
        return b.as_markup()

    @staticmethod
    def payment_back() -> InlineKeyboardMarkup:
        b = InlineKeyboardBuilder()
        b.button(text="⬅️ Назад", callback_data=AdminFlowCallback(action="back").pack())
        b.adjust(2)
        return b.as_markup()

    @staticmethod
    def back_to_shipment(cargo_id: int) -> InlineKeyboardMarkup:
        b = InlineKeyboardBuilder()
        b.button(text="⬅ Назад к посылке", callback_data=AdminFlowCallback(action="open", id=cargo_id).pack())
        b.adjust(1)
        return b.as_markup()

    @staticmethod
    def fsm_nav(cargo_id: int) -> InlineKeyboardMarkup:
        b = InlineKeyboardBuilder()
        b.button(text="⬅️ Назад",  callback_data=AdminFlowCallback(action="back",            id=cargo_id).pack())
        b.button(text="❌ Отмена", callback_data=AdminFlowCallback(action="payment_cancel",  id=cargo_id).pack())
        b.adjust(2)
        return b.as_markup()

    @staticmethod
    def shipment_moderation(cargo_id: int) -> InlineKeyboardMarkup:
        b = InlineKeyboardBuilder()
        b.button(text="✅ Принять",    callback_data=AdminFlowCallback(action="accept_send", id=cargo_id).pack())
        b.button(text="❌ Отклонить", callback_data=AdminFlowCallback(action="reject_send", id=cargo_id).pack())
        b.adjust(2)
        return b.as_markup()

    @staticmethod
    def status_picker(cargo_id: int) -> InlineKeyboardMarkup:
        b = InlineKeyboardBuilder()
        b.button(text="✏️ Редактируется",    callback_data=AdminFlowCallback(action="set_status", status='open',     id=cargo_id).pack())
        b.button(text="⏳ Ожидает решения",  callback_data=AdminFlowCallback(action="set_status", status='pending',  id=cargo_id).pack())
        b.button(text="✅ Принята (закрыта)", callback_data=AdminFlowCallback(action="set_status", status='closed',   id=cargo_id).pack())
        b.button(text="❌ Отклонена",        callback_data=AdminFlowCallback(action="set_status", status='rejected', id=cargo_id).pack())
        b.button(text="🗄 Архив",            callback_data=AdminFlowCallback(action="set_status", status='archived', id=cargo_id).pack())
        b.button(text="⬅ Назад",            callback_data=AdminFlowCallback(action="open",                          id=cargo_id).pack())
        b.adjust(1, 1, 1, 1, 1, 1)
        return b.as_markup()
