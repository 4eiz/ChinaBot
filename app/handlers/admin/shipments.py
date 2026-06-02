from io import BytesIO

from aiogram import types, F, Router
from typing import Dict
from decimal import Decimal
from config import CLEAR_RATE

from keyboards import AdminFlowCallback, AdminKB
from app.handlers.services.pdf_export import PDFExportService
from app.utils import safe_delete
from media import PhotoBank


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
        await safe_delete(call.message)

        is_admin = await self.users.is_admin(user_id=call.from_user.id)
        if not is_admin:
            text = "⛔️ Нет прав"
            return await call.answer(text=text, show_alert=True)
        
        text = "🛠 <b>Админ-панель</b>\nВыберите раздел:"
        photo = PhotoBank.get_file('ADMIN_PANEL_IMAGE')

        kb = AdminKB.menu()
        await call.message.answer_photo(photo=photo, caption=text, reply_markup=kb)



    async def shipments(self, call: types.CallbackQuery, callback_data: AdminFlowCallback | None = None):
        await safe_delete(call.message)

        is_admin = await self.users.is_admin(user_id=call.from_user.id)
        if not is_admin:
            return await call.answer(text="⛔️ Нет прав", show_alert=True)

        tab = (callback_data.status if callback_data else None) or "shared"
        page = (callback_data.id if callback_data else None) or 1
        page = max(1, int(page))
        limit = 5
        offset = (page - 1) * limit

        if tab == "archived":
            scope = None
            archived = True
            title = "🗄 Архив"
        elif tab == "personal":
            scope = "personal"
            archived = False
            title = "👤 Личные"
        else:
            tab = "shared"
            scope = "shared"
            archived = False
            title = "👥 Общие"

        total = await self.cargo.cargos.count_admin_filtered(scope=scope, archived=archived)
        total_pages = max(1, (total + limit - 1) // limit)
        page = min(page, total_pages)
        offset = (page - 1) * limit

        cargos = await self.cargo.cargos.list_admin_filtered(scope=scope, archived=archived, limit=limit, offset=offset)

        text = f"📦 <b>Посылки</b> (админ) — {title} <code>[{page}/{total_pages}]</code>"
        kb = AdminKB.shipments_list(cargos=cargos, tab=tab, page=page, total_pages=total_pages, has_prev=page>1, has_next=page<total_pages)
        photo = PhotoBank.get_file('CARGOS_IMAGE')
        await call.message.answer_photo(photo=photo, caption=text, reply_markup=kb)


    async def open_shipment(self, call: types.CallbackQuery, callback_data: AdminFlowCallback):
        await safe_delete(call.message)

        cargo_id = callback_data.id

        info = await self.cargo.get_cargo_info(cargo_id=cargo_id)
        if not info:
            text = "❌ Посылка не найдена"
            return await call.answer(text=text, show_alert=True)

        cargo = info["cargo"]
        cargo_type_name = info.get("cargo_type_name") or "—"
        legs = info["pricing"]
        item_count = info["items_count"]
        user_count = info["users_count"]
        sum_cny = info["sum_cny"]
        sum_usd_by_user = info["sum_usd_by_user"]
        sum_usd_clear = info["sum_usd_clear"]
        profit = info["profit"]

        sum_cny_str = f"{sum_cny.quantize(Decimal('0.01'))} ¥"
        sum_usd_user_str = f"{sum_usd_by_user:.2f}$"
        sum_usd_clear_str = f"{sum_usd_clear:.2f}$"
        profit_str = f"{profit:.2f}$"

        
        # --- owner/scope info ---
        scope_label = "👥 Общая" if cargo.get("scope") == "shared" else "👤 Личная"
        owner_line = ""
        if cargo.get("scope") != "shared":
            owner_id = cargo.get("owner_user_id")
            if owner_id:
                u = await self.users.get_user(user_id=int(owner_id)) or {}
                fio = " ".join(filter(None, [
                    u.get("name") or u.get("first_name"),
                    u.get("surname") or u.get("last_name"),
                ])).strip() or "—"
                phone = (u.get("phone_number") or u.get("phone")) or "—"
                owner_line = f"👤 Владелец: <code>{owner_id}</code> — {fio} (📱 <code>{phone}</code>)\n"
            else:
                owner_line = "👤 Владелец: —\n"
        text = (
            f"📦 <b>Посылка <code>#{cargo_id}</code></b>\n"
            f"{scope_label}\n"
            f"{owner_line}"
            f"🏷 Тип: <code>{cargo_type_name}</code>\n"
            f"🔖 Редактирование: <code>{cargo['status']}</code>\n"
            f"💵 Стоимость: <code>{cargo.get('payment_status') or '—'}</code>\n"
            f"⚖️ Вес: <code>{legs['total_weight_kg']} кг</code>\n"
            f"💰 CN→MSK: <code>{legs['cn_to_msk']['delivery_cost_usd']}$</code>\n"
            f"💰 MSK→BY: <code>{legs['msk_to_by']['delivery_cost_usd']}$</code>\n"
            f"\n"
            f"🧩 Товаров: <code>{item_count}</code>\n"
            f"👥 Юзеров: <code>{user_count}</code>\n"
            f"💴 Сумма (<b>CNY</b>): <code>{sum_cny_str}</code>\n"
            f"💵 Сумма (<b>USD</b>): <code>{sum_usd_user_str}</code>\n"
            f"💵 Сумма (<b>USD</b>, честный <code>{CLEAR_RATE}</code>): <code>{sum_usd_clear_str}</code>\n"
            f"📈 Прибыль: <b><code>{profit_str}</code></b>\n"
        )
        kb = AdminKB.shipment_view(cargo=cargo)
        await call.message.answer(text=text, reply_markup=kb)


    # --------------- статусы ---------------


    async def status_menu(self, call: types.CallbackQuery, callback_data: AdminFlowCallback):
        await safe_delete(call.message)

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
        await safe_delete(call.message)

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
        await safe_delete(call.message)
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

            referral_discount = float(row.get("referral_discount_usd", 0) or 0)
            finance_lines = [goods_line, msk_line, by_line]
            if referral_discount > 0:
                finance_lines.append(f"👥 Реф. скидка: <code>-{referral_discount:.2f}$</code>")
            finance_text = "\n".join(finance_lines)

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
                f"{finance_text}\n{summary}"
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
                tg_file = await bot.get_file(file_id)
                buf = BytesIO()
                await bot.download(tg_file, destination=buf)
                result[it["id"]] = buf.getvalue()
            except Exception:
                pass

        return result
