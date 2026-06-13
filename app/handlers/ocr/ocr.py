from io import BytesIO
from typing import Dict, Any, Optional
import asyncio

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

import config
from app.handlers.ocr.ocr_fsm import OCRState
from keyboards.ocr import (
    OCRKB,
    OCREditFieldCallback,
    OCRFlowCallback,
    OCRTypeCallback,
    OCRScopeCallback,
    OCRPersonalCargoCallback,
)
from app.handlers.services.ocr_parser import OCRParser
from app.handlers.services.recognition import RecognitionClient
from database import CargoService


TARIFF_PRIORITY = {
    "household": 1,   # хозтовары — самый дешёвый
    "shoes": 2,       # обувь — средний
    "clothes": 3,     # одежда — самый дорогой
}



class OCRHandler:
    """
    Скриншот → распознавание → отчёт (кандидаты) → правки →
    инструкция → фото товара → наименование → ссылка →
    тип товара → тип посылки → финальный превью → добавить/отмена.
    """

    def __init__(self, bot, conn=None):
        self.router = Router()
        self.bot = bot
        self.recognizer = RecognitionClient()
        self.cargo_service = CargoService(conn=conn) if conn else None

        # Входящее фото: либо скрин (OCR), либо фото товара (если ждём его)
        self.router.message.register(self.on_photo, F.photo)

        # Правки
        self.router.callback_query.register(self.on_edit_field, OCREditFieldCallback.filter(), OCRState.editing)
        self.router.message.register(self.on_new_value, F.text, OCRState.awaiting_value)

        # Фото товара
        self.router.message.register(self.on_product_photo, F.photo, OCRState.awaiting_product_photo)

        # Наименование / ссылка
        self.router.message.register(self.on_title, F.text, OCRState.awaiting_title)
        self.router.message.register(self.on_link, F.text, OCRState.awaiting_link)

        # Выбор типа / посылки / личной посылки
        self.router.callback_query.register(self.on_choose_type, OCRTypeCallback.filter())
        self.router.callback_query.register(self.on_choose_scope, OCRScopeCallback.filter())
        self.router.callback_query.register(self.on_choose_personal_cargo, OCRPersonalCargoCallback.filter())

        # Общий флоу
        self.router.callback_query.register(self.on_flow, OCRFlowCallback.filter())

    # --------------------------- Приём фото ---------------------------

    async def on_photo(self, message: Message, state: FSMContext):
        """
        Принимает фото и возвращает предположения
        """

        current = await state.get_state()
        if current in (OCRState.awaiting_product_photo.state, OCRState.waiting_instruction.state):
            await self._handle_product_photo(message=message, state=state)
            return

        # Скриншот → скачиваем и прогресс
        image_bytes, file_id = await self._download_largest_photo(message)

        steps = [
            "Фото загружено",
            "Получение токена",
            "Токен получен",
            "Отправка фото на распознавание",
            "Распознавание фото",
        ]
        total = len(steps)

        await self._progress_step(message.chat.id, state, steps[0], 1, total)
        await self._progress_step(message.chat.id, state, steps[1], 2, total)
        try:
            if hasattr(self.recognizer, "ensure_token"):
                await self.recognizer.ensure_token()
        except Exception:
            pass
        await self._progress_step(message.chat.id, state, steps[2], 3, total)
        await self._progress_step(message.chat.id, state, steps[3], 4, total)

        raw = await self.recognizer.recognize(image_bytes)
        await self._progress_step(message.chat.id, state, steps[4], 5, total)

        parsed = OCRParser.parse(raw)

        await state.update_data(
            ocr=parsed,
            source_screenshot_file_id=file_id,
            current_field=None,
            product_photo_file_id=None,
            title=None,
            source_url=None,
            item_type_code=None,
            scope=None,
            cargo_id=None,
        )

        text = self._render_report_with_candidates(ocr=parsed)
        kb = OCRKB.edit_menu()
        await self._replace_message(message.chat.id, state, text=text, reply_markup=kb)
        await state.set_state(OCRState.editing)

    # --------------------------- Правки ---------------------------

    async def on_edit_field(self, call: CallbackQuery, callback_data: OCREditFieldCallback, state: FSMContext):
        """
        Основаня функция отображения товара во время редактирования
        """

        field = callback_data.field  # price|quantity|color|size|title
        await state.update_data(current_field=field)

        readable = {
            "price": "цену (число)",
            "quantity": "количество (число)",
            "color": "цвет",
            "size": "размер",
            "title": "наименование товара (например: футболка, наушники, лего)",
        }.get(field, field)

        text = (
            f"✍️ Введите {readable}.\n\n"
            "<blockquote>Можно вставить один из вариантов из отчёта выше или ввести свой.\n"
            "⚠️ Используйте только если ИИ распознал значения неправильно!</blockquote>"
        )

        kb = OCRKB.back_to_edit()
        await self._replace_message(call.message.chat.id, state, text=text, reply_markup=kb)
        await state.set_state(OCRState.awaiting_value)
        await call.answer()

    async def on_new_value(self, message: Message, state: FSMContext):
        """
        Изменение значения товара
        """

        data = await state.get_data()
        field = data.get("current_field")
        if not field:
            text = "Поле не выбрано. Вернитесь в меню."
            kb = OCRKB.edit_menu()
            await self._replace_message(message.chat.id, state, text=text, reply_markup=kb)
            await state.set_state(OCRState.editing)
            return

        raw = message.text.strip()
        try:
            if field == "price":
                value = float(raw.replace(",", "."))
            elif field == "quantity":
                value = int(float(raw.replace(",", ".")))
                if value < 1:
                    raise ValueError
            else:
                value = raw
        except ValueError:
            text = "🚫 Некорректное значение. Попробуйте ещё раз."
            kb = OCRKB.back_to_edit()
            await self._replace_message(message.chat.id, state, text=text, reply_markup=kb)
            return

        ocr = data.get("ocr", {})
        ocr.setdefault(field, {"best": None, "candidates": []})
        ocr[field]["best"] = value
        s = str(value)
        if s not in (ocr[field]["candidates"] or []):
            ocr[field]["candidates"].append(s)

        await state.update_data(ocr=ocr, current_field=None)

        text = self._render_report_with_candidates(ocr=ocr, header="✏️ Обновлено:")
        kb = OCRKB.edit_menu()
        await self._replace_message(message.chat.id, state, text=text, reply_markup=kb)
        await state.set_state(OCRState.editing)

    # --------------------------- Флоу навигации ---------------------------

    async def on_flow(self, call: CallbackQuery, callback_data: OCRFlowCallback, state: FSMContext):
        action = callback_data.action
        data = await state.get_data()

        if action == "next_to_instruction":
            text = (
                "<b>📸 Отправьте фото самого товара</b>\n\n"
                "<blockquote>Если не знаете, где его взять — откройте инструкцию по кнопке ниже.</blockquote>"
            )
            kb = OCRKB.instruction(url=config.GUIDE_LINK)
            await self._replace_message(call.message.chat.id, state, text=text, reply_markup=kb)
            await state.set_state(OCRState.waiting_instruction)
            await call.answer()
            return

        if action == "back_to_edit":
            ocr = data.get("ocr", {})
            header = "<b>🔎 Текущие данные:</b>"

            text = self._render_report_with_candidates(ocr=ocr, header=header)
            kb = OCRKB.edit_menu()
            await self._replace_message(call.message.chat.id, state, text=text, reply_markup=kb)
            await state.set_state(OCRState.editing)
            await call.answer()
            return

        if action == "back_after_link":
            text = "<b>📝 Укажите наименование товара</b> (например: <code>футболка</code>, <code>наушники</code>, <code>лего</code>)"
            back = "next_to_instruction"
            kb = OCRKB.back_to_edit(back=back)
            await self._replace_message(call.message.chat.id, state, text=text, reply_markup=kb)
            await state.set_state(OCRState.awaiting_title)
            await call.answer()
            return

        if action == "back_after_type":
            text = "<b>🔗 Пришлите ссылку на товар</b>"
            back = "back_after_link"
            kb = OCRKB.back_to_edit(back=back)
            await self._replace_message(call.message.chat.id, state, text=text, reply_markup=kb)
            await state.set_state(OCRState.awaiting_link)
            await call.answer()
            return

        if action == "back_after_scope":
            text = "<b>🧰 Выберите тип товара:</b>"
            kb = OCRKB.type_menu()
            await self._replace_message(call.message.chat.id, state, text=text, reply_markup=kb)
            await state.set_state(OCRState.choosing_type)
            await call.answer()
            return
        
        if action == "confirm_upgrade":
            # апгрейдим тип посылки и идём к превью
            data = await state.get_data()
            cargo_id = int(data.get("cargo_id"))
            item_code = data.get("item_type_code")

            # получить id типа по коду
            new_type_id = await self.cargo_service.cargo_types.get_id_by_code(code=item_code)
            if new_type_id:
                await self.cargo_service.cargos.set_cargo_type(cargo_id=cargo_id, cargo_type_id=int(new_type_id))

            await self._show_final_preview(chat_id=call.message.chat.id, state=state)
            await state.set_state(OCRState.final_confirm)
            await call.answer()
            return

        if action == "confirm_add_cheaper":
            # ничего не меняем, просто продолжаем
            await self._show_final_preview(chat_id=call.message.chat.id, state=state)
            await state.set_state(OCRState.final_confirm)
            await call.answer()
            return

        if action == "cancel_mismatch":
            # вернём пользователя к выбору типа товара
            kb = OCRKB.type_menu()
            await self._replace_message(call.message.chat.id, state, text="<b>🧰 Выберите тип товара</b>:", reply_markup=kb)
            await state.set_state(OCRState.choosing_type)
            await call.answer()
            return


        if action == "confirm_final":
            if not self.cargo_service:
                text = "❗️Сервис грузов не инициализирован."
                await self._replace_message(call.message.chat.id, state, text=text, reply_markup=None)
                await call.answer()
                return

            ocr = data.get("ocr", {})
            user_id = call.from_user.id
            title = data.get("title") or ocr.get("title", {}).get("best") or "Без названия"
            source_url = data.get("source_url")
            product_photo_id = data.get("product_photo_file_id")
            item_type_code = data.get("item_type_code")
            scope = data.get("scope")
            cargo_id = data.get("cargo_id")

            price = ocr.get("price", {}).get("best") or 0
            qty = int(ocr.get("quantity", {}).get("best") or 1)
            color = ocr.get("color", {}).get("best")
            size = ocr.get("size", {}).get("best")

            extra = {"source_screenshot_file_id": data.get("source_screenshot_file_id")}

            if scope == "shared":
                await self.cargo_service.add_item_to_shared(
                    user_id=user_id,
                    item_type_code=item_type_code,
                    title=title,
                    photo_file_id=product_photo_id,
                    price=price,
                    quantity=qty,
                    color=color,
                    size=size,
                    source_url=source_url,
                    extra=extra,
                )
            else:
                await self.cargo_service.add_item_to_personal(
                    user_id=user_id,
                    item_type_code=item_type_code,
                    title=title,
                    cargo_id=cargo_id,
                    confirm_mixed=True,
                    photo_file_id=product_photo_id,
                    price=price,
                    quantity=qty,
                    color=color,
                    size=size,
                    source_url=source_url,
                    extra=extra,
                )

            text = ("<b>✅ Товар сохранён</b>\n"
                    "<i>Пропишите команду</i> /start"
                )
            await self._replace_message(call.message.chat.id, state, text=text, reply_markup=None)
            await state.clear()
            await call.answer()
            return

        if action == "cancel_final":
            text = "Вы действительно хотите отменить добавление товара?"
            kb = OCRKB.confirm_cancel()
            await self._replace_message(call.message.chat.id, state, text=text, reply_markup=kb)
            await call.answer()
            return

        if action == "confirm_cancel_yes":
            await self._replace_message(call.message.chat.id, state, text="❌ Добавление товара отменено.", reply_markup=None)
            await state.clear()
            await call.answer()
            return

        if action == "confirm_cancel_no":
            await self._show_final_preview(chat_id=call.message.chat.id, state=state)
            await state.set_state(OCRState.final_confirm)
            await call.answer()
            return

        await call.answer("Неизвестное действие")

    # --------------------------- Фото товара ---------------------------

    async def on_product_photo(self, message: Message, state: FSMContext):
        await self._handle_product_photo(message=message, state=state)

    async def _handle_product_photo(self, message: Message, state: FSMContext):
        _, file_id = await self._download_largest_photo(message)
        await state.update_data(product_photo_file_id=file_id)
        await message.delete()

        text = "<b>📝 Укажите наименование товара</b> (например: <code>футболка</code>, <code>наушники</code>, <code>лего</code>)"
        back = "next_to_instruction"
        kb = OCRKB.back_to_edit(back=back)
        await self._replace_message(message.chat.id, state, text=text, reply_markup=kb)
        await state.set_state(OCRState.awaiting_title)

    # --------------------------- Наименование / Ссылка ---------------------------

    async def on_title(self, message: Message, state: FSMContext):
        await message.delete()
        title = message.text.strip()
        await state.update_data(title=title)

        text = "<b>🔗 Пришлите ссылку на товар</b>"
        back = "back_after_link"
        kb = OCRKB.back_to_edit(back=back)
        await self._replace_message(message.chat.id, state, text=text, reply_markup=kb)
        await state.set_state(OCRState.awaiting_link)

    async def on_link(self, message: Message, state: FSMContext):
        await message.delete()
        link = message.text.strip()
        if link == "-":
            link = None
        await state.update_data(source_url=link)

        text = "<b>🧰 Выберите тип товара</b>:"
        kb = OCRKB.type_menu()
        await self._replace_message(message.chat.id, state, text=text, reply_markup=kb)
        await state.set_state(OCRState.choosing_type)

    # --------------------------- Выбор типа/посылки ---------------------------

    async def on_choose_type(self, call: CallbackQuery, callback_data: OCRTypeCallback, state: FSMContext):
        await state.update_data(item_type_code=callback_data.code)

        text = "<b>📦 Выберите тип посылки</b>: <code>общая</code> или <code>личная</code>"
        kb = OCRKB.scope_menu()
        await self._replace_message(call.message.chat.id, state, text=text, reply_markup=kb)
        await state.set_state(OCRState.choosing_scope)
        await call.answer()

    async def on_choose_scope(self, call: CallbackQuery, callback_data: OCRScopeCallback, state: FSMContext):
        scope = callback_data.scope
        await state.update_data(scope=scope)

        if scope == "shared":
            await self._show_final_preview(chat_id=call.message.chat.id, state=state)
            await state.set_state(OCRState.final_confirm)
            await call.answer()
            return

        # Личная посылка → список
        if not self.cargo_service:
            await self._replace_message(call.message.chat.id, state, text="❗️Сервис грузов не инициализирован.", reply_markup=None)
            await call.answer()
            return

        user_id = call.from_user.id
        cargos = await self.cargo_service.cargos.list_open_personal_by_user(user_id=user_id)

        if not cargos:
            text = (
                "🙅‍♂️ У вас нет личных открытых посылок.\n\n"
                "<i>Если нужна личная посылка — создайте её в профиле.</i>"
            )
            kb = OCRKB.personal_cargos([])
            await self._replace_message(call.message.chat.id, state, text=text, reply_markup=kb)
            await state.set_state(OCRState.choosing_personal_cargo)
            await call.answer()
            return

        text = "👤 Выберите вашу <b>личную посылку</b>:"
        kb = OCRKB.personal_cargos(cargos)
        await self._replace_message(call.message.chat.id, state, text=text, reply_markup=kb)
        await state.set_state(OCRState.choosing_personal_cargo)
        await call.answer()

    async def on_choose_personal_cargo(self, call: CallbackQuery, callback_data: OCRPersonalCargoCallback, state: FSMContext):
        await state.update_data(cargo_id=int(callback_data.cargo_id))

        data = await state.get_data()
        item_code = data.get("item_type_code")  # clothes|shoes|household
        cargo_id = int(callback_data.cargo_id)

        cargo = await self.cargo_service.cargos.get(cargo_id=cargo_id)
        if not cargo:
            await self._replace_message(call.message.chat.id, state, text="❌ Посылка не найдена.", reply_markup=None)
            await call.answer()
            return

        cargo_code = await self._cargo_type_code(cargo["cargo_type_id"])  # code
        if not item_code or not cargo_code:
            # если что-то не выбрано — идём дальше (старое поведение)
            await self._show_final_preview(chat_id=call.message.chat.id, state=state)
            await state.set_state(OCRState.final_confirm)
            await call.answer()
            return

        item_pri  = TARIFF_PRIORITY.get(item_code, 0)
        cargo_pri = TARIFF_PRIORITY.get(cargo_code, 0)

        # 1) Товар дороже текущего тарифа посылки → предупредить, что тариф вырастет и будет изменён
        if item_pri > cargo_pri:
            text = (
                "⚠️ <b>Тип вашего товара дороже текущего тарифа посылки.</b>\n\n"
                f"🧰 Товар: <b>{self._human_item_type(item_code)}</b>\n"
                f"📦 Посылка сейчас: <b>{self._human_item_type(cargo_code)}</b>\n\n"
                "Если продолжите, <b>стоимость доставки за кг увеличится</b>, и тип посылки будет изменён на более дорогой.\n\n"
                "Продолжить?"
            )
            await self._replace_message(call.message.chat.id, state, text=text, reply_markup=OCRKB.mismatch_upgrade())
            await call.answer()
            return

        # 2) Товар дешевле тарифа посылки → предупредить про возможную переплату для тяжёлых товаров
        if item_pri < cargo_pri:
            text = (
                "ℹ️ <b>Товар дешевле текущего тарифа посылки.</b>\n\n"
                f"🧰 Товар: <b>{self._human_item_type(item_code)}</b>\n"
                f"📦 Посылка: <b>{self._human_item_type(cargo_code)}</b>\n\n"
                "Посылка считается по <b>максимальному тарифу внутри</b>. Если товар тяжёлый, вы <b>переплатите за доставку</b>.\n"
                "Рекомендуем для тяжёлых хозтоваров создавать отдельную посылку.\n\n"
                "Всё равно добавить этот товар в текущую посылку?"
            )
            await self._replace_message(call.message.chat.id, state, text=text, reply_markup=OCRKB.mismatch_cheaper())
            await call.answer()
            return

        # 3) Равны → просто вперёд
        await self._show_final_preview(chat_id=call.message.chat.id, state=state)
        await state.set_state(OCRState.final_confirm)
        await call.answer()


    def _human_item_type(self, code: str) -> str:
        return {"clothes":"Одежда","shoes":"Обувь","household":"Хозтовары"}.get(code, code or "—")



    # --------------------------- Превью/вывод ---------------------------

    async def _show_final_preview(self, chat_id: int, state: FSMContext):
        data = await state.get_data()
        ocr = data.get("ocr", {})
        product_photo_id = data.get("product_photo_file_id")

        caption = self._render_final_preview(
            ocr=ocr,
            title=data.get("title"),
            product_photo_id=product_photo_id,
            source_url=data.get("source_url"),
            item_type_code=data.get("item_type_code"),
            scope=data.get("scope"),
            cargo_id=data.get("cargo_id"),
        )
        kb = OCRKB.final_actions()

        if product_photo_id:
            await self._replace_with_photo(chat_id, state, photo_file_id=product_photo_id, caption=caption, reply_markup=kb)
        else:
            await self._replace_message(chat_id, state, text=caption, reply_markup=kb)

    # --------------------------- Технические утилиты ---------------------------

    async def _replace_message(self, chat_id: int, state: FSMContext, text: str, reply_markup: Optional[Any]):
        data = await state.get_data()
        last_id = data.get("last_bot_message_id")
        if last_id:
            try:
                await self.bot.delete_message(chat_id=chat_id, message_id=last_id)
            except Exception:
                pass
        sent = await self.bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML", reply_markup=reply_markup)
        await state.update_data(last_bot_message_id=sent.message_id)

    async def _replace_with_photo(self, chat_id: int, state: FSMContext, photo_file_id: str, caption: str, reply_markup=None):
        data = await state.get_data()
        last_id = data.get("last_bot_message_id")
        if last_id:
            try:
                await self.bot.delete_message(chat_id=chat_id, message_id=last_id)
            except Exception:
                pass
        sent = await self.bot.send_photo(chat_id=chat_id, photo=photo_file_id, caption=caption, parse_mode="HTML", reply_markup=reply_markup)
        await state.update_data(last_bot_message_id=sent.message_id)

    async def _progress_step(self, chat_id: int, state: FSMContext, label: str, step_index: int, total_steps: int,
                             min_delay: float = 0, bar_len: int = 10):
        pct = max(0.0, min(1.0, step_index / total_steps))
        filled = int(round(bar_len * pct))
        empty = bar_len - filled
        bar = f"{'▰'*filled}{'▱'*empty} {int(pct*100)}%"
        text = f"⏳ {label}\n\n{bar}"
        await self._replace_message(chat_id, state, text=text, reply_markup=None)
        if min_delay > 0:
            await asyncio.sleep(min_delay)

    async def _download_largest_photo(self, message: Message) -> tuple[bytes, str]:
        largest = message.photo[-1]
        file_id = largest.file_id
        tg_file = await self.bot.get_file(file_id)
        buf = BytesIO()
        await self.bot.download(tg_file, destination=buf)
        buf.seek(0)
        return buf.read(), file_id

    # --------------------------- Рендеринг текстов ---------------------------

    def _render_report_with_candidates(self, ocr: Dict[str, Dict[str, Any]], header: str = "🔎 Что удалось найти:") -> str:
        def line(field: str, label: str) -> str:
            best = ocr.get(field, {}).get("best")
            candidates = ocr.get(field, {}).get("candidates") or []
            best_str = "—" if best in (None, "") else str(best)
            extra = ""
            if len(candidates) > 1:
                bullets = "\n".join(f"• <code>{c}</code>" for c in candidates)
                extra = (
                    "\n<i>Найдено несколько вариантов — выберите поле для правки и "
                    "введите один из вариантов ниже (или свой):</i>\n" + bullets
                )
            return f"{label}: <code>{best_str}</code>{extra}"

        title_best = ocr.get("title", {}).get("best") or "—"
        price_line = line("price", "💰 Цена")
        qty_line = line("quantity", "🔢 Кол-во")
        color_line = line("color", "🎨 Цвет")
        size_line = line("size", "📏 Размер")

        return (
            f"<b>{header}</b>\n\n"
            f"🏷 Наименование: <code>{title_best}</code>\n"
            f"{price_line}\n{qty_line}\n{color_line}\n{size_line}\n"
            "\n<blockquote>Нажмите на кнопку нужного поля, чтобы изменить значение.\n"
            "⚠️ Используйте это только, если ИИ распознал значения неправильно!</blockquote>"
        )

    def _render_final_preview(
        self,
        ocr: Dict[str, Dict[str, Any]],
        title: Optional[str],
        product_photo_id: Optional[str],
        source_url: Optional[str] = None,
        item_type_code: Optional[str] = None,
        scope: Optional[str] = None,
        cargo_id: Optional[int] = None,
    ) -> str:
        title_str = title or ocr.get("title", {}).get("best") or "—"
        price_str = ocr.get("price", {}).get("best")
        qty_str = ocr.get("quantity", {}).get("best")
        color_str = ocr.get("color", {}).get("best") or "—"
        size_str = ocr.get("size", {}).get("best") or "—"

        price_view = "—" if price_str in (None, "") else str(price_str)
        qty_view = "—" if qty_str in (None, "") else str(qty_str)
        photo_note = "🖼 Фото товара: <b>есть</b>" if product_photo_id else "🖼 Фото товара: <b>нет</b>"

        type_map = {"clothes": "Одежда", "shoes": "Обувь", "household": "Хозтовары", None: "—"}
        type_view = type_map.get(item_type_code, item_type_code or "—")

        scope_view = "—"
        if scope == "shared":
            scope_view = "Общая посылка"
        elif scope == "personal":
            scope_view = f"Личная посылка (ID: {cargo_id})" if cargo_id else "Личная посылка"

        url_line = f"🔗 Ссылка: <a href=\"{source_url}\">открыть</a>" if source_url else "🔗 Ссылка: —"

        return (
            "🧾 <b>Проверьте карточку товара</b>\n\n"
            f"🏷 Наименование: <code>{title_str}</code>\n"
            f"💰 Цена: <code>{price_view}</code>\n"
            f"🔢 Кол-во: <code>{qty_view}</code>\n"
            f"🎨 Цвет: <code>{color_str}</code>\n"
            f"📏 Размер: <code>{size_str}</code>\n"
            f"{url_line}\n"
            f"🧰 Тип товара: <b>{type_view}</b>\n"
            f"📦 Посылка: <b>{scope_view}</b>\n"
            f"{photo_note}\n\n"
            "Нажмите «➕ Добавить» для подтверждения или «❌ Отмена»."
        )


    async def _cargo_type_code(self, cargo_type_id: int) -> str | None:
        row = await self.cargo_service.cargo_types.get(cargo_type_id=cargo_type_id)
        return (row or {}).get("code")
