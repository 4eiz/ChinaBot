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


    async def notify_new_shipment_request(self, *, cargo_service, cargo: dict, username):
        if not self.admin_chat_id:
            return

        await cargo_service.cargos.recalc_weight_and_count(cargo_id=cargo["id"])

        # ---- базовая часть (как у тебя)
        user = None
        uline = f"@{username}" if username else "без username"
        fio = "Нету"
        user_id_display = "—"

        user_id = cargo.get("owner_user_id")
        if user_id is not None:
            try:
                user = await cargo_service.users.get_user(user_id=int(user_id))   # :contentReference[oaicite:3]{index=3}
            except Exception:
                user = None

        if user:
            fio = f"{(user.get('name') or '').strip()} {(user.get('surname') or '').strip()}".strip() or "Нету"
            user_id_display = user.get('id') or user_id
        else:
            uline = "<code>Общая</code>"
            user_id_display = user_id if user_id is not None else "—"

        tariff = await cargo_service.cargo_types.get_name_by_id(
            cargo_type_id=cargo["cargo_type_id"]
        ) or "—"

        # ------- суммы по товарам (как у тебя) -------
        rows = await cargo_service.items.list_by_cargo(cargo_id=cargo["id"])      # :contentReference[oaicite:4]{index=4}
        total_cny = Decimal("0")
        for r in rows:
            price = Decimal(str(r.get("price") or 0))
            qty = Decimal(str(r.get("quantity") or 1))
            total_cny += (price * qty)

        total_usd = Decimal("0")
        user_ids = await cargo_service.items.users_in_cargo(cargo_id=cargo["id"]) # :contentReference[oaicite:5]{index=5}
        for uid in user_ids:
            goods_usd, _ = await cargo_service.items.totals_for_user_in_cargo(
                cargo_id=cargo["id"], user_id=int(uid)
            )                                                                      # :contentReference[oaicite:6]{index=6}
            total_usd += goods_usd

        real_usd = (total_cny * CLEAR_RATE)

        total_cny  = total_cny.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        total_usd  = total_usd.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        real_usd   = real_usd.quantize(Decimal("0.01"),  rounding=ROUND_HALF_UP)
        profit_usd = (total_usd - real_usd).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        kb = AdminKB.shipment_moderation(cargo_id=cargo["id"])

        # --------- ТЕКСТ ШАПКИ ---------
        text = (
            "🆕 <b>Новая заявка на отправку посылки!</b>\n\n"
            f"👤 <b>{fio}</b>: {uline} (<b>ID</b>: <code>{user_id_display}</code>)\n"
            f"📦 <b>Номер посылки</b>: <code>#{cargo['id']}</code> | <code>{cargo.get('title') or 'Без названия'}</code>\n"
            f"💵 <b>Сумма товаров</b>: <code>{total_cny}¥</code> (~<code>{total_usd}$</code>)\n"
            f"💱 <b>Честная сумма</b>: <code>{real_usd}$</code> (<code>{CLEAR_RATE}</code>)\n"
            f"🛍️ <b>Количество товаров</b>: <code>{cargo.get('items_count', 0)}</code>\n"
            f"📊 <b>Тариф</b>: <code>{tariff}</code>\n"
        )

        # --------- СВОДКА ПО УЧАСТНИКАМ ДЛЯ ОБЩЕЙ ПОСЫЛКИ ---------
        if user is None:
            per_user_lines = []
            total_profit_shared = Decimal("0.00")

            # Пройдёмся по всем участникам
            for uid in user_ids:
                uid = int(uid)
                u = await cargo_service.users.get_user(user_id=uid) or {}          # :contentReference[oaicite:7]{index=7}
                user_rate = Decimal(str(u.get("rate") or "0"))
                # Товар в $ уже с учётом user.rate:
                goods_usd, _ = await cargo_service.items.totals_for_user_in_cargo(
                    cargo_id=cargo["id"], user_id=uid
                )                                                                  # :contentReference[oaicite:8]{index=8}

                # Сумма в CNY = goods_usd / user_rate (если курс > 0)
                sum_cny = goods_usd / user_rate if user_rate > 0 else Decimal("0")

                # Прибыль по формуле: CNY*rate_user - CNY*CLEAR_RATE
                profit_user = (sum_cny * user_rate) - (sum_cny * CLEAR_RATE)
                profit_user = profit_user.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                total_profit_shared += profit_user

                fio_user = " ".join(filter(None, [
                    u.get("name") or u.get("first_name"),
                    u.get("surname") or u.get("last_name"),
                ])).strip() or str(uid)

                per_user_lines.append(
                    f"• <b>{fio_user}</b> (<code>{uid}</code>): "
                    f"товар <code>{goods_usd.quantize(Decimal('0.01'))}$</code>, "
                    f"курс <code>{user_rate}</code> → "
                    f"прибыль <b><code>{profit_user}$</code></b>"
                )

            total_profit_shared = total_profit_shared.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            text += "\n👥 <b>Сводка по участникам</b>:\n" + "\n".join(per_user_lines) + \
                    f"\n\n💹 <b>Итого прибыль (общая)</b>: <code>{total_profit_shared}$</code>\n"

        else:
            # персональный кейс — как было
            text += f"\n💹 <b>Прибыль</b>: <code>{profit_usd}$</code>\n"

        # ---- отправка
        await self.bot.send_message(
            chat_id=self.admin_chat_id,
            text=text,
            reply_markup=kb,
            parse_mode="HTML",
        )