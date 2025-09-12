from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup
from .callback_data import ProfileFlowCallback, ShipmentFlowCallback, AdminFlowCallback




class ProfileKB:

    @staticmethod
    def main_menu(*, is_admin: bool = False) -> InlineKeyboardMarkup:
        b = InlineKeyboardBuilder()
        b.button(text="📦 Мои посылки", callback_data=ProfileFlowCallback(action="shipments").pack())
        if is_admin:
            b.button(text="🛠 Админ-панель", callback_data=AdminFlowCallback(action="menu").pack())
        b.button(text="⬅ Назад", callback_data=ProfileFlowCallback(action="back").pack())
        b.adjust(1, 1, 1)
        return b.as_markup()
    

class ShipmentsKB:
    @staticmethod
    def list_shipments(cargos: list[dict], mode: str = "personal") -> InlineKeyboardMarkup:
        b = InlineKeyboardBuilder()

        # табы
        b.button(text=("📦 Личные ✅" if mode=="personal" else "📦 Личные"),
                callback_data=ProfileFlowCallback(action="shipments").pack())
        b.button(text=("👥 Общие ✅" if mode=="shared" else "👥 Общие"),
                callback_data=ProfileFlowCallback(action="shipments_shared").pack())

        # список
        if cargos:
            for c in cargos:
                title = c.get("title") or f"Посылка #{c['id']}"
                b.button(text=f"📦 {title}", callback_data=ShipmentFlowCallback(action="open", id=c["id"]).pack())

        # создать — только для личных
        if mode == "personal":
            b.button(text="➕ Создать посылку", callback_data=ShipmentFlowCallback(action="create").pack())

        b.button(text="⬅ Назад", callback_data=ProfileFlowCallback(action="back_to_profile").pack())

        # раскладка: табы -> список -> сервисные
        sizes: list[int] = [2]
        if cargos:
            sizes += [1] * len(cargos)
        if mode == "personal":
            sizes.append(1)
        sizes.append(1)
        b.adjust(*sizes)
        return b.as_markup()

    @staticmethod
    def choose_type() -> InlineKeyboardMarkup:
        b = InlineKeyboardBuilder()
        b.button(text="🧥 Одежда", callback_data=ShipmentFlowCallback(action="type", cargo_type='clothes').pack())
        b.button(text="👟 Обувь", callback_data=ShipmentFlowCallback(action="type", cargo_type='shoes').pack())
        b.button(text="🧼 Хозтовары", callback_data=ShipmentFlowCallback(action="type", cargo_type='household').pack())
        b.button(text="📦 Смешанный", callback_data=ShipmentFlowCallback(action="type", cargo_type='mixed').pack())
        b.adjust(1)
        return b.as_markup()

    @staticmethod
    def confirm() -> InlineKeyboardMarkup:
        b = InlineKeyboardBuilder()
        b.button(text="✅ Подтвердить", callback_data=ShipmentFlowCallback(action="confirm").pack())
        b.button(text="⬅ Назад", callback_data=ShipmentFlowCallback(action="back_to_name").pack())
        b.adjust(2)
        return b.as_markup()

    @staticmethod
    def view_shipment(cargo_id: int):
        b = InlineKeyboardBuilder()
        b.button(
            text="🛒 Товары",
            callback_data=ShipmentFlowCallback(action="list_items", id=cargo_id, page=1).pack()
        )
        b.button(
            text="📄 Экспорт PDF",
            callback_data=ShipmentFlowCallback(action="export_pdf", id=cargo_id).pack()
        )
        b.button(
            text="⬅ Назад",
            callback_data=ProfileFlowCallback(action="shipments").pack()
        )
        b.adjust(1)
        return b.as_markup()


    @staticmethod
    def items(
        cargo_id: int,
        items: list[dict],
        page: int,
        has_prev: bool,
        has_next: bool,
        limit: int = 5
    ):
        b = InlineKeyboardBuilder()

        # Кнопки-товары (каждый товар — отдельная кнопка)
        for idx, it in enumerate(items, start=1 + (page - 1) * limit):
            title = it.get("title", "—")
            qty = it.get("quantity", 0)
            price = it.get("price", 0)
            b.button(
                text=f"{idx}. {title} ×{qty} — {price}¥",
                callback_data=ShipmentFlowCallback(
                    action="view_item",
                    id=cargo_id,
                    item_id=it["id"],
                    page=page
                ).pack()
            )

        # Пагинация
        if has_prev:
            b.button(
                text="◀️",
                callback_data=ShipmentFlowCallback(
                    action="items_prev",
                    id=cargo_id,
                    page=page - 1
                ).pack()
            )
        if has_next:
            b.button(
                text="▶️",
                callback_data=ShipmentFlowCallback(
                    action="items_next",
                    id=cargo_id,
                    page=page + 1
                ).pack()
            )

        # Назад к посылке
        b.button(
            text="⬅ Назад",
            callback_data=ShipmentFlowCallback(
                action="open",
                id=cargo_id
            ).pack()
        )

        # layout: по одному товару в строке, затем стрелки (если есть), затем «Назад»
        sizes: list[int] = []
        if items:
            sizes += [1] * len(items)
        if has_prev or has_next:
            sizes.append(2 if (has_prev and has_next) else 1)
        sizes.append(1)  # Назад
        b.adjust(*sizes)

        return b.as_markup()

    @staticmethod
    def item_view(cargo_id: int, item_id: int, *, can_edit: bool) -> InlineKeyboardMarkup:
        b = InlineKeyboardBuilder()
        if can_edit:
            b.button(
                text="🗑 Удалить",
                callback_data=ShipmentFlowCallback(
                    action="delete_item", id=cargo_id, item_id=item_id
                ).pack()
            )
        b.button(
            text="⬅ Назад к товарам",
            callback_data=ShipmentFlowCallback(action="list_items", id=cargo_id, page=1).pack()
        )
        b.adjust(1)
        return b.as_markup()
    
    @staticmethod
    def send_confirm(cargo_id: int) -> InlineKeyboardMarkup:
        b = InlineKeyboardBuilder()
        b.button(text="✅ Да, отправить", callback_data=ShipmentFlowCallback(action="send_yes", id=cargo_id).pack())
        b.button(text="❌ Нет, вернуться", callback_data=ShipmentFlowCallback(action="open", id=cargo_id).pack())
        b.adjust(2)
        return b.as_markup()
    

    @staticmethod
    def open_shipment(cargo_id: int) -> InlineKeyboardMarkup:
        b = InlineKeyboardBuilder()
        b.button(text="Открыть посылку", callback_data=ShipmentFlowCallback(action="open", id=cargo_id).pack())
        return b.as_markup()



class ShipmentViewKB:
    @staticmethod
    def main(cargo: dict) -> InlineKeyboardMarkup:
        b = InlineKeyboardBuilder()
        b.button(
            text="🛒 Товары",
            callback_data=ShipmentFlowCallback(action="list_items", id=cargo["id"], page=1).pack()
        )
        b.button(
            text="📄 Экспорт (мои товары)",
            callback_data=ShipmentFlowCallback(action="export_user_pdf", id=cargo["id"]).pack()
        )

        # кнопка отправки только если статус == open
        if cargo.get("status") == "open":
            b.button(
                text="📨 Отправить посылку",
                callback_data=ShipmentFlowCallback(action="send_request", id=cargo["id"]).pack()
            )

        b.button(
            text="⬅ Назад",
            callback_data=ProfileFlowCallback(action="shipments").pack()
        )

        # раскладка: товары + экспорт всегда, кнопка отправки (если есть), назад
        sizes = [1, 1]
        if cargo.get("status") == "open":
            sizes.append(1)
        sizes.append(1)
        b.adjust(*sizes)

        return b.as_markup()

    @staticmethod
    def add_send_button(cargo_id: int) -> InlineKeyboardMarkup:
        """
        Отдельная клавиатура (можно использовать рядом с основным меню посылки).
        """
        b = InlineKeyboardBuilder()
        b.button(text="📨 Отправить посылку", callback_data=ShipmentFlowCallback(action="send_request", id=cargo_id).pack())
        b.adjust(1)
        return b.as_markup()