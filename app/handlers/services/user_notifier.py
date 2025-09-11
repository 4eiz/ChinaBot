from aiogram import Bot
from typing import Optional


class UserNotifier:
    """
    Уведомления пользователю о статусе отправки посылки.
    Использует HTML-разметку. Все тексты с эмодзи и аккуратным форматированием.
    """

    def __init__(self, *, bot: Bot):
        self.bot = bot

    # -------------------- БАЗОВЫЕ МЕТОДЫ (когда у тебя уже есть cargo и user_id) --------------------

    async def shipment_rejected(self, *, user_id: int, cargo: dict) -> None:
        """
        Уведомляет пользователя, что заявка на отправку посылки отклонена.
        """
        title = (cargo.get("title") or "Без названия")
        text = (
            "❌ <b>Заявка отклонена</b>\n\n"
            f"📦 Посылка: <code>#{cargo['id']}</code> | {title}\n"
            "🛠 Проверь состав посылки (убери лишнее/исправь данные) и попробуй отправить снова."
        )
        await self.bot.send_message(chat_id=user_id, text=text, parse_mode="HTML")

    async def shipment_accepted(self, *, user_id: int, cargo: dict) -> None:
        """
        Уведомляет пользователя, что заявка на отправку посылки принята.
        """
        title = (cargo.get("title") or "Без названия")
        text = (
            "✅ <b>Заявка принята</b>\n\n"
            f"📦 Посылка: <code>#{cargo['id']}</code> | {title}\n"
            "📥 Мы начинаем обработку. Спасибо!"
        )
        await self.bot.send_message(chat_id=user_id, text=text, parse_mode="HTML")

    # -------------------- УДОБНЫЕ МЕТОДЫ (когда есть только cargo_id) --------------------

    async def shipment_rejected_by_id(self, *, cargo_service, cargo_id: int) -> None:
        """
        Достаёт данные и вызывает shipment_rejected(...).
        """
        cargo = await cargo_service.cargos.get(cargo_id=cargo_id)
        if not cargo:
            return
        user_id = int(cargo.get("owner_user_id"))
        await self.shipment_rejected(user_id=user_id, cargo=cargo)

    async def shipment_accepted_by_id(self, *, cargo_service, cargo_id: int) -> None:
        """
        Достаёт данные и вызывает shipment_accepted(...).
        """
        cargo = await cargo_service.cargos.get(cargo_id=cargo_id)
        if not cargo:
            return
        user_id = int(cargo.get("owner_user_id"))
        await self.shipment_accepted(user_id=user_id, cargo=cargo)