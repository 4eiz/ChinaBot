from config import CLEAR_RATE

from aiogram import Bot, types
from typing import Optional
from keyboards import AdminKB
from decimal import Decimal, ROUND_HALF_UP

from . import shipment_exporter



class AdminNotifier:
    def __init__(self, *, bot: Bot, admin_chat_id: Optional[int]):
        self.bot = bot
        self.admin_chat_id = admin_chat_id
        self.excel_export = shipment_exporter

    async def notify_status_edit(self, *, cargo_id: int, new_status: str):
        if not self.admin_chat_id:
            return
        text = f"✏️ Посылка #{cargo_id}: статус редактирования → <b>{new_status}</b>"
        await self.bot.send_message(chat_id=self.admin_chat_id, text=text)

    async def notify_payment_status(self, *, cargo_id: int, new_status: str):
        if not self.admin_chat_id:
            return
        text = f"💳 Посылка #{cargo_id}: статус оплаты → <b>{new_status}</b>"
        await self.bot.send_message(chat_id=self.admin_chat_id, text=text)

    async def notify_route_status(self, *, cargo_id: int, new_status: str):
        if not self.admin_chat_id:
            return
        text = f"🚚 Посылка #{cargo_id}: маршрут → <b>{new_status}</b>"
        await self.bot.send_message(chat_id=self.admin_chat_id, text=text)

    async def notify_payment_added(self, *, cargo_id: int, user_id: int, kind: str, amount: str, currency: str):
        if not self.admin_chat_id:
            return
        text = f"💵 Платёж: посылка #{cargo_id}, user {user_id}, {kind} — {amount} {currency}"
        await self.bot.send_message(chat_id=self.admin_chat_id, text=text)

    async def notify_new_shipment_request(self, *, cargo_service, cargo: dict, username):
        if not self.admin_chat_id:
            return

        await cargo_service.cargos.recalc_weight_and_count(cargo_id=cargo["id"])

        user_id = cargo.get("owner_user_id", None)
        if user_id:
            user = await cargo_service.users.get_user(user_id=user_id)
            uline = f"@{username}" if username is not None else "без username"
            fio = f"{user.get('name')} {user.get('surname')}"

        else:
            uline = "<code>Общая</code>"
            fio = "Нету"

        tariff = await cargo_service.cargo_types.get_name_by_id(
            cargo_type_id=cargo["cargo_type_id"]
        ) or "—"

        # ------- суммы по товарам -------
        rows = await cargo_service.items.list_by_cargo(cargo_id=cargo["id"])
        total_cny = Decimal("0")
        for r in rows:
            price = Decimal(str(r.get("price") or 0))
            qty = Decimal(str(r.get("quantity") or 1))
            total_cny += (price * qty)

        total_usd = Decimal("0")
        user_ids = await cargo_service.items.users_in_cargo(cargo_id=cargo["id"])
        for uid in user_ids:
            goods_usd, _ = await cargo_service.items.totals_for_user_in_cargo(
                cargo_id=cargo["id"], user_id=uid
            )
            total_usd += goods_usd

        real_usd = (total_cny * CLEAR_RATE)

        total_cny = total_cny.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        total_usd = total_usd.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        real_usd  = real_usd.quantize(Decimal("0.01"),  rounding=ROUND_HALF_UP)
        profit_usd = (total_usd - real_usd).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        kb = AdminKB.shipment_moderation(cargo_id=cargo["id"])

        text = (
            "🆕 <b>Новая заявка на отправку посылки!</b>\n\n"
            f"👤 <b>{fio}</b>: {uline} (<b>ID</b>: <code>{user.get('id')}</code>)\n"
            f"📦 <b>Номер посылки</b>: <code>#{cargo['id']}</code> | <code>{cargo.get('title') or 'Без названия'}</code>\n"
            f"💵 <b>Сумма товаров</b>: <code>{total_cny}¥</code> (~<code>{total_usd}$</code>)\n"
            f"💱 <b>Честная сумма</b>: <code>{real_usd}$</code> (<code>{CLEAR_RATE}</code>)\n"
            f"🛍️ <b>Количество товаров</b>: <code>{cargo.get('items_count', 0)}</code>\n"
            f"📊 <b>Тариф</b>: <code>{tariff}</code>\n\n"
            f"💹 <b>Прибыль</b>: <code>{profit_usd}$</code>"
        )

        # 1) Сначала сообщение
        await self.bot.send_message(
            chat_id=self.admin_chat_id,
            text=text,
            reply_markup=kb,
            parse_mode="HTML",
        )

        # 2) Затем Excel-файл (как в твоём примере PDF)
        # excel = ExcelExportService()
        excel_china_to_msk_object = self.excel_export.ExcelExportService(bot=self.bot)
        file_path = await excel_china_to_msk_object.generate_goods_sheet(cargo_service=cargo_service, cargo_id=cargo["id"])

        file = types.FSInputFile(file_path)
        caption = f"📄 Экспорт посылки #{cargo['id']} (Карго)"
        await self.bot.send_document(
            chat_id=self.admin_chat_id,
            document=file,
            caption=caption,
        )

        excel_msk_to_by_object = self.excel_export.ExcelTextFormExportService()
        file_path = await excel_msk_to_by_object.generate_text_form(cargo_service=cargo_service, cargo_id=cargo["id"])

        file = types.FSInputFile(file_path)
        caption = f"📄 Экспорт посылки #{cargo['id']} (Садовод)"
        await self.bot.send_document(
            chat_id=self.admin_chat_id,
            document=file,
            caption=caption,
        )
