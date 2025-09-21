from io import BytesIO
import os, tempfile
from typing import Dict

from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, FSInputFile

from keyboards import ShipmentsKB, ProfileFlowCallback, ShipmentFlowCallback, ShipmentViewKB
from app.handlers.profile.fsm import ShipmentFSM
from database import CargoService, UsersDB
from app.handlers.services.pdf_export import PDFExportService
from app.handlers.services.admin_notifier import AdminNotifier

from config import bot, ADMIN_CHAT_ID



class ShipmentsHandler:
    """Хендлер для работы с посылками."""

    def __init__(self, conn):
        self.router = Router()
        self.cargo_service = CargoService(conn=conn)
        self.users = UsersDB(conn=conn)
        self.pdf_service = PDFExportService()

        # регистрируем хендлеры
        self.router.callback_query.register(self.list_shipments, ProfileFlowCallback.filter(F.action == "shipments"))
        self.router.callback_query.register(self.list_shared_shipments, ProfileFlowCallback.filter(F.action == "shipments_shared"))
        self.router.callback_query.register(self.create_shipment, ShipmentFlowCallback.filter(F.action == "create"))
        self.router.callback_query.register(self.choose_type, ShipmentFlowCallback.filter(F.action == "type"), ShipmentFSM.type)
        self.router.message.register(self.msg_input_name, ShipmentFSM.name)
        self.router.callback_query.register(self.confirm, ShipmentFlowCallback.filter(F.action == "confirm"), ShipmentFSM.confirm)
        self.router.callback_query.register(self.back_to_name, ShipmentFlowCallback.filter(F.action == "back_to_name"), ShipmentFSM.confirm)
        self.router.callback_query.register(self.view_shipment, ShipmentFlowCallback.filter(F.action == "open"))
        self.router.callback_query.register(self.list_items, ShipmentFlowCallback.filter(F.action.in_(["list_items", "items_prev", "items_next"])))
        self.router.callback_query.register(self.view_item, ShipmentFlowCallback.filter(F.action == "view_item"))
        self.router.callback_query.register(self.delete_item, ShipmentFlowCallback.filter(F.action == "delete_item"))
        self.router.callback_query.register(self.export_user_pdf, ShipmentFlowCallback.filter(F.action == "export_user_pdf"))

        self.router.callback_query.register(self.send_request, ShipmentFlowCallback.filter(F.action == "send_request"))
        self.router.callback_query.register(self.send_yes,      ShipmentFlowCallback.filter(F.action == "send_yes"))
        self.router.callback_query.register(self.send_no,       ShipmentFlowCallback.filter(F.action == "send_no"))



    async def list_shipments(self, call: types.CallbackQuery):
        # ЛИЧНЫЕ
        await call.message.delete()
        user_id = call.from_user.id
        cargos = await self.cargo_service.cargos.list_by_user(user_id=user_id)  # личные
        text = "📦 Ваши ЛИЧНЫЕ посылки:" if cargos else "У вас пока нет личных посылок."
        data = [dict(c) for c in cargos]
        kb = ShipmentsKB.list_shipments(cargos=data, mode="personal")
        await call.message.answer(text=text, reply_markup=kb)


    async def list_shared_shipments(self, call: types.CallbackQuery):
        # ОБЩИЕ, где у юзера есть товары
        await call.message.delete()

        user_id = call.from_user.id
        cargos = await self.cargo_service.cargos.list_shared_by_user_participation(user_id=user_id)
        
        text = "👥 Общие посылки, где есть ваши товары:" if cargos else "В общих посылках ваших товаров пока нет."
        data = [dict(c) for c in cargos]
        kb = ShipmentsKB.list_shipments(cargos=data, mode="shared")
        await call.message.answer(text=text, reply_markup=kb)


    async def create_shipment(self, call: types.CallbackQuery, state: FSMContext):
        await call.message.delete()
        
        kb = ShipmentsKB.choose_type()
        text = "Выберите тип посылки:"

        await call.message.answer(text=text, reply_markup=kb)
        await state.set_state(ShipmentFSM.type)


    async def choose_type(self, call: types.CallbackQuery, callback_data: ShipmentFlowCallback, state: FSMContext):
        await call.message.delete()
        
        cargo_type = callback_data.cargo_type  # clothes / shoes / household / mixed
        await state.update_data(type=cargo_type)
        await state.set_state(ShipmentFSM.name)

        text = "✏️ Введите название посылки (до 20 символов):"
        await call.message.answer(text=text)


    async def msg_input_name(self, message: types.Message, state: FSMContext):
        await message.delete()

        message_id = message.message_id - 1
        chat_id = message.from_user.id
        await message.bot.delete_message(chat_id=chat_id, message_id=message_id)
        name = message.text.strip()[:20]
        await state.update_data(name=name)

        data = await state.get_data()
        text = (
            f"📦 <b>Новая посылка</b>\n\n"
            f"<b>Тип:</b> <code>{data['type']}</code>\n"
            f"<b>Название:</b> <code>{data['name']}</code>\n\n"
            "<blockquote>Подтверждаете?</blockquote>"
        )
        kb = ShipmentsKB.confirm()

        await message.answer(text=text, reply_markup=kb)
        await state.set_state(ShipmentFSM.confirm)


    async def confirm(self, call: types.CallbackQuery, state: FSMContext):
        await call.message.delete()

        data = await state.get_data()
        cargo_type_id = await self.cargo_service.cargo_types.get_id_by_code(code=data["type"])
        # print(f'ID: {cargo_type_id}')

        data_ship = await self.cargo_service.cargos.create(
            scope="personal",
            cargo_type_id=cargo_type_id,
            owner_user_id=call.from_user.id,
            title=data["name"]
        )
        await state.clear()

        text = "✅ Посылка создана!"
        cargo_id = data_ship.get('id')
        kb = ShipmentsKB.open_shipment(cargo_id=cargo_id)
        await call.message.answer(text=text, reply_markup=kb)


    async def back_to_name(self, call: types.CallbackQuery, state: FSMContext):
        await call.message.delete()

        await state.set_state(ShipmentFSM.name)
        text = "<b>✏️ Введите название посылки (до 20 символов):</b>"
        await call.message.answer(text=text)

    async def view_shipment(self, call: types.CallbackQuery, callback_data: ShipmentFlowCallback):
        await call.message.delete()

        cargo_id = callback_data.id
        cargo = await self.cargo_service.cargos.get(cargo_id=cargo_id)
        if not cargo:
            await call.answer("❌ Посылка не найдена", show_alert=True)
            return

        type_row = await self.cargo_service.cargo_types.get(cargo_type_id=cargo["cargo_type_id"])
        type_name = type_row["name"] if type_row else "—"

        pricing2 = await self.cargo_service.compute_pricing_two_legs(cargo_id=cargo_id)

        text = (
            f"📦 <b>Посылка</b>\n\n"
            f"🏷️ <b>Название:</b> <code>{cargo['title'] or '—'}</code>\n"
            f"📂 <b>Тип:</b> <code>{type_name}</code>\n"
            f"🔖 <b>Редактирование:</b> <code>{cargo['status']}</code>\n"
            f"💵 <b>Оплата:</b> <code>{cargo.get('payment_status')}</code>\n"
            f"🚚 <b>Маршрут:</b> <code>{cargo.get('route_status')}</code>\n"
            f"⚖️ <b>Вес:</b> <code>{pricing2['total_weight_kg']} кг</code>\n"
            f"💰 <b>Доставка CN→MSK:</b> <code>{pricing2['cn_to_msk']['delivery_cost_usd']}$</code>\n"
            f"💰 <b>Доставка MSK→BY:</b> <code>{pricing2['msk_to_by']['delivery_cost_usd']}$</code>\n"
        )

        kb = ShipmentViewKB.main(cargo=cargo)
        await call.message.answer(text=text, reply_markup=kb)



    async def list_items(self, call: types.CallbackQuery, callback_data: ShipmentFlowCallback):
        await call.message.delete()

        cargo_id = callback_data.id
        page = callback_data.page or 1
        limit = 5
        offset = (page - 1) * limit
        user_id = call.from_user.id

        cargo = await self.cargo_service.cargos.get(cargo_id=cargo_id)
        if not cargo:
            await call.answer("❌ Посылка не найдена", show_alert=True)
            return

        if cargo["scope"] == "shared":
            total = await self.cargo_service.items.count_by_cargo_for_user(cargo_id=cargo_id, user_id=user_id)
            items = await self.cargo_service.items.list_by_cargo_for_user_paginated(
                cargo_id=cargo_id, user_id=user_id, limit=limit, offset=offset
            )
            title_prefix = "<blockquote>👥 (общая, показываю ТОЛЬКО ваши товары)</blockquote>"
        else:
            total = await self.cargo_service.items.count_by_cargo(cargo_id=cargo_id)
            items = await self.cargo_service.items.list_by_cargo_paginated(
                cargo_id=cargo_id, limit=limit, offset=offset
            )
            title_prefix = "<blockquote>👤 (личная)</blockquote>"

        total_pages = max(1, (total + limit - 1) // limit)
        has_prev = page > 1
        has_next = page < total_pages

        text = f"🛒 <b>Товары в посылке #{cargo_id}</b>\n{title_prefix}\n<code>[{page}/{total_pages}]</code>"

        kb = ShipmentsKB.items(
            cargo_id=cargo_id,
            items=items,
            page=page,
            has_prev=has_prev,
            has_next=has_next
        )
        await call.message.answer(text=text, reply_markup=kb)


    async def export_user_pdf(self, call: types.CallbackQuery, callback_data: ShipmentFlowCallback):
        # await call.message.delete()

        cargo_id = callback_data.id
        user_id = call.from_user.id

        cargo = await self.cargo_service.cargos.get(cargo_id=cargo_id)
        if not cargo:
            await call.answer("❌ Посылка не найдена", show_alert=True)
            return

        # берём только ТВОИ товары (в общей — это must; в личной — тоже корректно)
        items = await self.cargo_service.items.list_by_cargo_for_user_paginated(
            cargo_id=cargo_id, user_id=user_id, limit=10_000, offset=0
        )

        if not items:
            text = "Похоже, у вас нет товаров в этой посылке."
            await call.message.answer(text=text)
            return

        # расчёт сводки и выбор строки по пользователю
        settlement = await self.cargo_service.settlement_by_cargo(cargo_id=cargo_id)
        row = next((r for r in settlement["users"] if r["user_id"] == user_id), None)
        if not row:
            text = "Не удалось собрать сводку по оплатам."
            await call.message.answer(text=text)
            return

        # тянем миниатюры по file_id
        photos = await self._collect_item_photos(bot=call.bot, items=items)

        # готовим PDF для юзера
        tmpdir = tempfile.gettempdir()  # на Linux → /tmp, на Windows → C:\Users\...\AppData\Local\Temp
        file_path = os.path.join(tmpdir, f"cargo_{cargo_id}_user_{user_id}.pdf")

        user = await self.users.get_user(user_id=user_id)

        pdf = PDFExportService()
        path = pdf.generate_user_cart_pdf(
            file_path=file_path,
            cargo=cargo,
            user=user,
            items=items,
            settlement_row=row,
            photos=photos,  # {item_id: bytes}
        )

        text = "📄 Ваш отчёт по товарам в этой посылке"
        await call.message.answer_document(document=FSInputFile(file_path), caption=text)

    async def _collect_item_photos(self, *, bot, items: list[dict]) -> Dict[int, bytes]:
        """
        Возвращает {item_id: image_bytes} для тех, где есть photo_file_id.
        """
        result: Dict[int, bytes] = {}
        for it in items:
            file_id = it.get("photo_file_id")
            if not file_id:
                continue
            try:
                file = await bot.get_file(file_id)  # aiogram 3.x
                buf = BytesIO()
                await bot.download_file(file.file_path, buf)
                result[it["id"]] = buf.getvalue()
            except Exception:
                # пропускаем, если файл не доступен
                pass
        return result


    async def view_item(self, call: types.CallbackQuery, callback_data: ShipmentFlowCallback):
        await call.message.delete()

        cargo_id = callback_data.id
        item_id = callback_data.item_id
        user_id = call.from_user.id

        cargo = await self.cargo_service.cargos.get(cargo_id=cargo_id)
        item = await self.cargo_service.items.get(item_id=item_id)
        user_data = await self.users.get_user(user_id=user_id)
        rate = user_data.get('rate')

        if not cargo or not item:
            await call.answer("❌ Товар или посылка не найдены", show_alert=True)
            return

        if cargo["scope"] == "shared" and item["user_id"] != user_id:
            await call.answer("⛔️ Это не ваш товар.", show_alert=True)
            fake_cb = ShipmentFlowCallback(action="list_items", id=cargo_id, page=1)
            await self.list_items(call, fake_cb)
            return

        can_edit = (cargo.get("status") == "open") and (item["user_id"] == user_id)

        text = (
            f"🛍 <b>{item['title']}</b>\n\n"
            f"💰 Цена: <code>{(item['price'] * rate * item['quantity']):.2f}$</code>\n"
            f"📦 Количество: <code>{item['quantity']}</code>\n"
            f"⚖️ Вес: <code>{item['weight_kg']} кг</code>\n"
        )
        if item.get("color"):
            text += f"🎨 Цвет: <code>{item['color']}</code>\n"
        if item.get("size"):
            text += f"📏 Размер: <code>{item['size']}</code>\n"
        if item.get("options"):
            text += f"⚙️ Опции: <code>{item['options']}</code>\n"

        kb = ShipmentsKB.item_view(cargo_id=cargo_id, item_id=item_id, can_edit=can_edit)

        if item.get("photo_file_id"):
            await call.message.answer_photo(photo=item["photo_file_id"], caption=text, reply_markup=kb)
        else:
            await call.message.answer(text=text, reply_markup=kb)


    async def delete_item(self, call: types.CallbackQuery, callback_data: ShipmentFlowCallback):
        # await call.message.delete()
        item_id = callback_data.item_id
        cargo_id = callback_data.id
        user_id = call.from_user.id

        cargo = await self.cargo_service.cargos.get(cargo_id=cargo_id)
        item = await self.cargo_service.items.get(item_id=item_id)
        if not cargo or not item:
            text = "❌ Не удалось найти товар или посылку"
            await call.answer(text=text, show_alert=True)
            return

        if cargo.get("status") != "open":
            text = "⛔️ Посылка закрыта. Редактирование запрещено."
            await call.answer(text=text, show_alert=True)
            fake_cb = ShipmentFlowCallback(action="list_items", id=cargo_id, page=1)
            await self.list_items(call, fake_cb)
            return

        if cargo["scope"] == "shared" and item["user_id"] != user_id:
            text = "⛔️ Нельзя удалить чужой товар."
            await call.answer(text=text, show_alert=True)
            fake_cb = ShipmentFlowCallback(action="list_items", id=cargo_id, page=1)
            await self.list_items(call, fake_cb)
            return

        deleted_cargo_id = await self.cargo_service.items.delete(item_id=item_id)
        if not deleted_cargo_id:
            text = "❌ Не удалось удалить товар"
            await call.answer(text=text, show_alert=True)
            return

        await self.cargo_service.cargos.recalc_weight_and_count(cargo_id=cargo_id)
        text = "🗑 Товар удалён"
        await call.answer(text=text, show_alert=True)
        fake_cb = ShipmentFlowCallback(action="list_items", id=cargo_id, page=1)
        await self.list_items(call, fake_cb)


    # ── send_request: проверка на пустую посылку ───────────────────────────────────
    async def send_request(self, call: types.CallbackQuery, callback_data: ShipmentFlowCallback, state: FSMContext):
        """
        Шаг 1: показать подтверждение перед отправкой.
        """
        cargo_id = int(callback_data.id)

        # 1) валидируем статус
        cargo = await self.cargo_service.cargos.get(cargo_id=cargo_id)
        if not cargo or cargo.get("status") != "open":
            return await call.answer("Эта посылка не редактируется или уже отправлена.", show_alert=True)

        # 2) валидируем наличие товаров (не удаляем сообщение до ответа!)
        await self.cargo_service.cargos.recalc_weight_and_count(cargo_id=cargo_id)
        cargo = await self.cargo_service.cargos.get(cargo_id=cargo_id)
        items_count = int(cargo.get("items_count") or 0)
        if items_count == 0:
            return await call.answer("❌ Нельзя отправить пустую посылку — добавьте хотя бы один товар.", show_alert=True)

        # 3) дальше всё как было
        await call.message.delete()
        text = (
            "❗ <b>Ты уверен, что посылка собрана полностью и лишнего нет?</b>\n\n"
            "После отправки изменить состав будет <u>невозможно</u> 🚫"
        )
        kb = ShipmentsKB.send_confirm(cargo_id=cargo_id)
        await call.message.answer(text=text, reply_markup=kb)
        await call.answer()


    # ── send_yes: повторная проверка перед сменой статуса ──────────────────────────
    async def send_yes(self, call: types.CallbackQuery, callback_data: ShipmentFlowCallback, state: FSMContext):
        """
        Шаг 2: юзер подтвердил — переводим в pending и шлём заявку админам.
        """
        cargo_id = int(callback_data.id)

        # 1) статус «open» обязателен
        cargo = await self.cargo_service.cargos.get(cargo_id=cargo_id)
        if not cargo or cargo.get("status") != "open":
            return await call.answer("Эта посылка не редактируется или уже отправлена.", show_alert=True)

        # 2) гарантируем актуальные агрегаты и проверяем, что не пусто
        await self.cargo_service.cargos.recalc_weight_and_count(cargo_id=cargo_id)
        cargo = await self.cargo_service.cargos.get(cargo_id=cargo_id)
        items_count = int(cargo.get("items_count") or 0)
        if items_count == 0:
            return await call.answer("❌ Нельзя отправить пустую посылку — добавьте хотя бы один товар.", show_alert=True)

        # 3) всё ок → переводим в pending
        await self.cargo_service.cargos.set_status(cargo_id=cargo_id, status="pending")

        # 4) уведомление админам
        notifier = AdminNotifier(bot=bot, admin_chat_id=ADMIN_CHAT_ID)
        cargo_now = await self.cargo_service.cargos.get(cargo_id=cargo_id)
        username = call.from_user.username
        await notifier.notify_new_shipment_request(cargo_service=self.cargo_service, cargo=cargo_now, username=username)

        # 5) пользователю
        await call.message.delete()
        await call.message.answer("✅ <b>Заявка отправлена</b>. Администратор скоро проверит посылку.")
        await call.answer()


    async def send_no(self, call: types.CallbackQuery, callback_data: ShipmentFlowCallback, state: FSMContext):
        """
        Шаг 2: юзер отменил подтверждение.
        """

        await call.message.delete()

        text = "🔙 Окей, вернулись к редактированию посылки."
        await call.message.answer(text=text)
        await call.answer()