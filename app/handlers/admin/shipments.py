import os
import tempfile
from io import BytesIO

from aiogram import types, F, Router
from typing import Dict

from keyboards import AdminFlowCallback, AdminKB
from app.handlers.services.pdf_export import PDFExportService


class AdminShipments:
    """
    Меню, список посылок, карточка, смена статуса, принятие/отклонение заявки.
    """
    def __init__(self, *, router: Router, cargo, users, notifier, user_notifier):
        self.router = router
        self.cargo = cargo
        self.users = users
        self.notifier = notifier
        self.user_notifier = user_notifier

        self.router.callback_query.register(self.menu, AdminFlowCallback.filter(F.action == "menu"))
        self.router.callback_query.register(self.shipments, AdminFlowCallback.filter(F.action == "shipments"))
        self.router.callback_query.register(self.open_shipment, AdminFlowCallback.filter(F.action == "open"))

        # статусы
        self.router.callback_query.register(self.status_menu, AdminFlowCallback.filter(F.action == "status"))
        self.router.callback_query.register(self.status_set, AdminFlowCallback.filter(F.action == "set_status"))

        # заявки
        self.router.callback_query.register(self.accept_send, AdminFlowCallback.filter(F.action == "accept_send"))
        self.router.callback_query.register(self.reject_send, AdminFlowCallback.filter(F.action == "reject_send"))

        # сводка пользователей
        self.router.callback_query.register(self.users_summary, AdminFlowCallback.filter(F.action == "summary"))


    # --------------- меню/навигация ---------------


    async def menu(self, call: types.CallbackQuery):
        await call.message.delete()

        is_admin = await self.users.is_admin(user_id=call.from_user.id)
        if not is_admin:
            text = "⛔️ Нет прав"
            return await call.answer(text=text, show_alert=True)
        
        text = "🛠 <b>Админ-панель</b>\nВыберите раздел:"
        kb = AdminKB.menu()
        await call.message.answer(text=text, reply_markup=kb)


    async def shipments(self, call: types.CallbackQuery):
        await call.message.delete()

        is_admin = await self.users.is_admin(user_id=call.from_user.id)
        if not is_admin:
            text = "⛔️ Нет прав"
            return await call.answer(text=text, show_alert=True)
        cargos = await self.cargo.cargos.list_all()

        text = "📦 <b>Посылки</b> (админ)"
        kb = AdminKB.shipments_list(cargos=cargos)
        await call.message.answer(text=text, reply_markup=kb)


    async def open_shipment(self, call: types.CallbackQuery, callback_data: AdminFlowCallback):
        await call.message.delete()

        cargo_id = callback_data.id
        cargo = await self.cargo.cargos.get(cargo_id=cargo_id)

        if not cargo:
            text = "❌ Посылка не найдена"
            return await call.answer(text=text, show_alert=True)

        legs = await self.cargo.compute_pricing_two_legs(cargo_id=cargo_id)

        text = (
            f"📦 <b>Посылка #{cargo_id}</b>\n"
            f"🔖 Редактирование: <code>{cargo['status']}</code>\n"
            f"💵 Стоимость: <code>{cargo.get('payment_status') or '—'}</code>\n"
            # f"🚚 Маршрут: <code>{cargo.get('route_status') or '—'}</code>\n"
            f"⚖️ Вес: <code>{legs['total_weight_kg']} кг</code>\n"
            f"💰 CN→MSK: <code>{legs['cn_to_msk']['delivery_cost_usd']}$</code>\n"
            f"💰 MSK→BY: <code>{legs['msk_to_by']['delivery_cost_usd']}$</code>\n"
        )
        kb = AdminKB.shipment_view(cargo=cargo)
        await call.message.answer(text=text, reply_markup=kb)


    # --------------- статусы ---------------


    async def status_menu(self, call: types.CallbackQuery, callback_data: AdminFlowCallback):
        await call.message.delete()

        cargo_id = callback_data.id
        cargo = await self.cargo.cargos.get(cargo_id=cargo_id)

        if not cargo:
            return await call.answer("❌ Посылка не найдена", show_alert=True)

        text = (
            "🔧 <b>Изменение статуса посылки</b>\n\n"
            f"📦 Посылка: <code>#{cargo_id}</code>\n"
            f"🔖 Текущий статус: <code>{cargo.get('status') or '—'}</code>\n\n"
            "Выберите новый статус:"
        )
        kb = AdminKB.status_picker(cargo_id=cargo_id)
        await call.message.answer(text=text, reply_markup=kb)


    async def status_set(self, call: types.CallbackQuery, callback_data: AdminFlowCallback):
        await call.answer()
        await call.message.delete()

        cargo_id = callback_data.id
        cargo = await self.cargo.cargos.get(cargo_id=cargo_id)
        if not cargo:
            text = "❌ Посылка не найдена"
            return await call.answer(text=text, show_alert=True)

        status = callback_data.status
        if not status:
            text = "❌ Неизвестный статус"
            return await call.answer(text=text, show_alert=True)

        if status == "pending" and cargo["status"] not in {"open", "rejected"}:
            return await call.answer("⚠️ В 'pending' можно перевести только из 'open' или 'rejected'.", show_alert=True)

        await self.cargo.cargos.set_status(cargo_id=cargo_id, status=status)

        EMO = {"open":"✏️","pending":"⏳","closed":"✅","rejected":"❌","archived":"🗄"}

        text = (
            "🔧 <b>Статус изменён</b>\n"
            f"📦 Посылка: <code>#{cargo_id}</code>\n"
            f"{EMO[status]} Новый статус: <code>{status}</code>"
        )
        kb = AdminKB.back_to_shipment(cargo_id=cargo_id)
        await call.message.answer(text=text, reply_markup=kb)


    # --------------- заявки ---------------


    async def accept_send(self, call: types.CallbackQuery, callback_data: AdminFlowCallback):
        await call.answer()

        cargo_id = int(callback_data.id)
        cargo = await self.cargo.cargos.get(cargo_id=cargo_id)
        if not cargo or cargo.get("status") != "pending":
            return await call.answer("Эта посылка не в статусе ожидания.", show_alert=True)

        await self.cargo.cargos.set_status(cargo_id=cargo_id, status="closed")

        new_text = "✅ <b>Посылка принята</b>"
        old_text = "🆕 <b>Новая заявка на отправку посылки!</b>"
        text = call.message.html_text.replace(old_text, new_text)
        await call.message.edit_text(text=text)

        await self.user_notifier.shipment_accepted_by_id(cargo_service=self.cargo, cargo_id=cargo_id)


    async def reject_send(self, call: types.CallbackQuery, callback_data: AdminFlowCallback):
        await call.answer()

        cargo_id = int(callback_data.id)
        cargo = await self.cargo.cargos.get(cargo_id=cargo_id)
        if not cargo or cargo.get("status") != "pending":
            return await call.answer("Эта посылка не в статусе ожидания.", show_alert=True)

        await self.cargo.cargos.set_status(cargo_id=cargo_id, status="open")

        new_text = "❌ <b>Посылка отклонена</b>"
        old_text = "🆕 <b>Новая заявка на отправку посылки!</b>"
        text = call.message.html_text.replace(old_text, new_text)
        await call.message.edit_text(text=text, parse_mode="HTML")

        await self.user_notifier.shipment_rejected_by_id(cargo_service=self.cargo, cargo_id=cargo_id)


    # --------------- сводка ---------------


    async def users_summary(self, call: types.CallbackQuery, callback_data: AdminFlowCallback):
        await call.message.delete()
        cargo_id = callback_data.id
        settle = await self.cargo.settlement_by_cargo(cargo_id=cargo_id)

        def line_for(label: str, due: float, paid: float) -> str:
            diff = round(paid - due, 2)
            if diff < 0:
                return f"{label}: <code>{due:.2f}$</code> (оплачено <code>{paid:.2f}$</code>) — 💳 к оплате <code>{-diff:.2f}$</code>"
            elif diff > 0:
                return f"{label}: <code>{due:.2f}$</code> (оплачено <code>{paid:.2f}$</code>) — 🔁 к возврату <code>{diff:.2f}$</code>"
            else:
                return f"{label}: <code>{due:.2f}$</code> (оплачено <code>{paid:.2f}$</code>)"

        lines: list[str] = []
        for row in settle["users"]:
            uid = row["user_id"]
            u = await self.users.get_user(user_id=uid) or {}
            fio = " ".join(filter(None, [
                u.get("name") or u.get("first_name"),
                u.get("surname") or u.get("last_name"),
            ])).strip() or "—"
            phone = (u.get("phone_number") or u.get("phone")) or "—"

            goods_line = line_for("🛍️ Товар", float(row["goods_usd"]), float(row["goods_paid_usd"]))
            msk_line = line_for("🚚 CN→MSK", float(row["msk_usd"]),float(row["msk_paid_usd"]))
            by_line = line_for("🚛 MSK→BY", float(row["by_usd"]), float(row["by_paid_usd"]))

            adv = float(row["advance_usd"])
            total_due  = float(row["total_due_usd"])
            total_over = float(row.get("total_overpay_usd", 0.0))

            net_due = max(round(total_due - total_over, 2), 0.0)
            net_refund = max(round(total_over - total_due, 2), 0.0)

            summary_lines = [f"💳 Аванс: <code>{adv:.2f}$</code>"]
            if net_due > 0:
                summary_lines.append(f"💰 Итого к оплате: <b><code>{net_due:.2f}$</code></b>")
            if net_refund > 0:
                summary_lines.append(f"🔁 Итого к возврату: <b><code>{net_refund:.2f}$</code></b>")
            summary = "\n".join(summary_lines)

            lines.append(
                f"👤 <b>{uid}</b> — {fio}\n"
                f"📱 <code>{phone}</code>\n"
                f"{goods_line}\n{msk_line}\n{by_line}\n{summary}"
            )

        text = "👥 <b>Сводка по людям</b>\n\n" + ("\n\n".join(lines) if lines else "Пусто")
        users = [r["user_id"] for r in settle["users"]]
        kb = AdminKB.summary_menu(cargo_id=cargo_id, users=users)
        await call.message.answer(text=text, reply_markup=kb)


    # -------------- утилиты (для экспорта PDF товаров) -------------


    async def _collect_item_photos(self, *, bot, items: list[dict]) -> Dict[int, bytes]:
        result: Dict[int, bytes] = {}

        for it in items:
            file_id = it.get("photo_file_id")
            if not file_id:
                continue
            try:
                tg_file = await bot.get_file(file_id)  # aiogram 3.x
                buf = BytesIO()
                await bot.download(tg_file, destination=buf)
                result[it["id"]] = buf.getvalue()
            except Exception:
                pass

        return result
