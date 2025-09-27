from decimal import Decimal
from aiogram import types, F, Router
from aiogram.fsm.context import FSMContext

from keyboards import AdminFlowCallback, AdminKB, PaymentFlowCallback
from .fsm import PaymentForm  # если FSM лежит рядом с админом; иначе поправь импорт


class AdminPayments:
    """
    Кнопочный флоу платежей:
    - выбор типа -> выбор суммы -> сохранить/комментарий
    - «Назад» со СУММ к ТИПАМ
    - «Назад к посылке» с ТИПОВ
    - запись в БД через self.pay.add(...)
    """

    def __init__(self, *, router: Router, cargo, pay, users):
        self.router = router
        self.cargo = cargo
        self.pay = pay
        self.users = users

        self.router.callback_query.register(self.add_payment, AdminFlowCallback.filter(F.action == "add_payment"))
        self.router.callback_query.register(self.add_payment, AdminFlowCallback.filter(F.action == "back"), PaymentForm.amount)

        self.router.callback_query.register(self.payment_pick_kind, AdminFlowCallback.filter(F.action == "payment"), PaymentForm.kind)
        self.router.callback_query.register(self.payment_pick_kind, AdminFlowCallback.filter(F.action == "back"), PaymentForm.note)

        self.router.message.register(self.payment_pick_custom_amount, PaymentForm.amount)        
        self.router.callback_query.register(self.payment_pick_amount, PaymentFlowCallback.filter(F.action == "pay_amount"))

        self.router.message.register(self.payment_note_entered, PaymentForm.note)
        self.router.callback_query.register(self.payment_save, AdminFlowCallback.filter(F.action == "pay_save"))
        self.router.callback_query.register(self.payment_add_note, AdminFlowCallback.filter(F.action == "pay_add_note"))
        self.router.callback_query.register(self.payment_cancel, AdminFlowCallback.filter(F.action == "payment_cancel"))


    async def add_payment(self, call: types.CallbackQuery, callback_data: AdminFlowCallback, state: FSMContext):
        await call.message.delete()

        data = await state.get_data()
        cargo_id = getattr(callback_data, "id", None) or data.get("cargo_id")
        user_id = getattr(callback_data, "user_id", None) or data.get("user_id")

        await state.clear()
        await state.update_data(cargo_id=cargo_id, user_id=user_id)
        await state.set_state(PaymentForm.kind)

        text = (
            "💵 <b>Новый платёж</b>\n"
            f"📦 Посылка: <code>#{cargo_id}</code>\n"
            f"👤 Пользователь: <code>{user_id}</code>\n\n"
            "<blockquote>Выберите тип:</blockquote>"
        )
        kb = AdminKB.payment_kind(cargo_id=cargo_id)
        await call.message.answer(text=text, reply_markup=kb)


    async def payment_pick_kind(self, call: types.CallbackQuery, callback_data: AdminFlowCallback, state: FSMContext):
        """
        Сохранение причины пополнения баланса

        Вывод сообщения о выборе сумммы
        """
        
        await call.answer()
        await call.message.delete()

        data = await state.get_data()
        kind = getattr(callback_data, "status", None) or data.get("kind")

        await state.update_data(kind=kind)
        await state.set_state(PaymentForm.amount)

        text = (
            f"🏷 Тип: <code>{kind}</code>\n"
            f"<blockquote>🧮 Выберите сумму или введите свою:</blockquote>"
        )
        kb = AdminKB.payment_amount()

        await call.message.answer(text=text, reply_markup=kb)


    async def payment_pick_custom_amount(self, message: types.Message, state: FSMContext):
        """
        Сохранение суммы
        """
        
        await message.delete()

        await state.set_state(PaymentForm.note)

        data = await state.get_data()
        kind = data.get("kind")

        try:
            amount = float(message.text.replace(',', '.'))

        except:
            text = "<blockquote>Введите число:</blockquote>"
            # kb = AdminKB.payment_back()
            await message.reply(text=text)

            await state.set_state(PaymentForm.amount)
            return

        await state.update_data(amount=amount, currency="USD")
        await message.delete()


        text = (
            f"🏷 Тип: <code>{kind}</code>\n"
            f"💵 Сумма: <code>{amount} USD</code>\n\n"
            "Сохранить платёж?"
        )
        kb = AdminKB.payment_note_choice()
        await message.answer(text=text, reply_markup=kb)


    async def payment_pick_amount(self, call: types.CallbackQuery, callback_data: PaymentFlowCallback, state: FSMContext):
        """
        Выбор суммы платежа по кнопкам
        """

        await call.answer()
        await call.message.delete()

        await state.set_state(PaymentForm.note)

        data = await state.get_data()
        kind = data.get("kind")

        amount = Decimal(callback_data.amount)
        await state.update_data(amount=amount, currency="USD")

        text = (
            f"🏷 Тип: <code>{kind}</code>\n"
            f"💵 Сумма: <code>{amount} USD</code>\n\n"
            "Сохранить платёж?"
        )
        kb = AdminKB.payment_note_choice()
        await call.message.answer(text=text, reply_markup=kb)


    async def payment_save(self, call: types.CallbackQuery, callback_data: AdminFlowCallback, state: FSMContext):
        """
        Финальное действие, сохрание платежа
        """

        await call.answer()
        await call.message.delete()

        data = await state.get_data()
        cargo_id = data["cargo_id"]
        user_id = data["user_id"]
        kind = data["kind"]
        amount = data["amount"]
        currency = data.get("currency", "USD")

        await self.pay.add(cargo_id=cargo_id, user_id=user_id, kind=kind, amount_usd=amount, note=None)
        await state.clear()

        text = (
            "✅ <b>Платёж сохранён</b>\n"
            f"📦 Посылка: <code>#{cargo_id}</code>\n"
            f"👤 Пользователь: <code>{user_id}</code>\n"
            f"🏷 Тип: <code>{kind}</code>\n"
            f"💵 Сумма: <code>{amount} {currency}</code>"
        )
        kb = AdminKB.back_to_shipment(cargo_id=cargo_id)
        await call.message.answer(text=text, reply_markup=kb)


    async def payment_add_note(self, call: types.CallbackQuery, callback_data: AdminFlowCallback, state: FSMContext):
        await call.answer()
        await call.message.delete()

        await state.set_state(PaymentForm.note)

        text = "📝 Отправьте комментарий или <code>-</code> если без комментария."
        kb = AdminKB.fsm_nav(cargo_id=callback_data.id)
        await call.message.answer(text=text, reply_markup=kb)


    async def payment_note_entered(self, message: types.Message, state: FSMContext):
        """
        Пользователь вводит комментарий к платежу (состояние PaymentForm.note).
        Сохраняем платёж с note и завершаем FSM.
        """
        note_text = (message.text or "").strip()
        if note_text in {"-", "—"}:
            note_text = None

        data = await state.get_data()
        cargo_id = data["cargo_id"]
        user_id = data["user_id"]
        kind = data["kind"]
        amount = Decimal(str(data["amount"]))
        currency = str(data.get("currency", "USD"))

        # # удаляем сообщение пользователя с комментом (по желанию)
        # with contextlib.suppress(Exception):
        #     await message.delete()

        # пишем платёж с комментарием
        await self.pay.add(
            cargo_id=cargo_id,
            user_id=user_id,
            kind=kind,
            amount_usd=amount,
            note=note_text,
        )

        await state.clear()

        text = (
            "✅ <b>Платёж сохранён</b>\n"
            f"📦 Посылка: <code>#{cargo_id}</code>\n"
            f"👤 Пользователь: <code>{user_id}</code>\n"
            f"🏷 Тип: <code>{kind}</code>\n"
            f"💵 Сумма: <code>{amount} {currency}</code>\n"
            f"📝 Комментарий: <code>{note_text or '—'}</code>"
        )
        kb = AdminKB.back_to_shipment(cargo_id=cargo_id)
        await message.answer(text=text, reply_markup=kb)



    async def payment_cancel(self, call: types.CallbackQuery, callback_data: AdminFlowCallback, state: FSMContext):
        await call.message.delete()
        await state.clear()

        text = "🚫 Операция добавления платежа отменена."
        kb = AdminKB.back_to_shipment(cargo_id=callback_data.id)
        await call.message.answer(text=text, reply_markup=kb)
