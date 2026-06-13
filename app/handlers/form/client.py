# app/handlers/form/client.py
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from app.handlers.form.fsm import FormState
from media import PhotoBank
from keyboards import FormKB, FormBackCallback, SourceCallback, ConfirmCallback, RequestsKB
import config

from database import RequestsDB



class FormClientHandler:
    def __init__(self, conn):
        # print(conn)
        self.router = Router()
        self.router.message.register(self.get_name, FormState.name)
        self.router.message.register(self.get_surname, FormState.surname)
        self.router.message.register(self.get_phone, FormState.phone)
        self.router.callback_query.register(self.get_source, SourceCallback.filter(), FormState.source)
        self.router.callback_query.register(self.go_back, FormBackCallback.filter())
        self.router.callback_query.register(self.confirm_form, ConfirmCallback.filter(F.action == "yes"), FormState.confirm)

        self.conn = conn

        self.text_preparation()


    async def get_name(self, message: Message, state: FSMContext):
        message_id = message.message_id
        await message.delete()
        chat_id = message.from_user.id
        await message.bot.delete_message(chat_id=chat_id, message_id=message_id-1)

        await state.update_data(name=message.text)
        await state.set_state(FormState.surname)

        step = 'name'
        kb = FormKB.back_keyboard(to_step=step)
        photo = PhotoBank.get_file('SLIDE2')
        await message.answer_photo(photo=photo, caption=self.text_surname, reply_markup=kb)


    async def get_surname(self, message: Message, state: FSMContext):
        message_id = message.message_id
        await message.delete()
        chat_id = message.from_user.id
        await message.bot.delete_message(chat_id=chat_id, message_id=message_id-1)

        await state.update_data(surname=message.text)
        await state.set_state(FormState.phone)

        kb = FormKB.contact_keyboard()
        photo = PhotoBank.get_file('SLIDE3')
        await message.answer_photo(photo=photo, caption=self.text_phone, reply_markup=kb)


    async def get_phone(self, message: Message, state: FSMContext):
        # Удаление последних сообщений
        await message.delete()
        try:
            await message.bot.delete_message(chat_id=message.chat.id, message_id=message.message_id - 1)
        except Exception:
            pass  # если вдруг уже удалено

        # Получение номера из контакта
        if message.contact:
            phone_number = message.contact.phone_number
        else:
            # Фолбэк, если контакт не отправлен (например, вручную ввёл)
            phone_number = message.text

        await state.update_data(phone=phone_number)
        await state.set_state(FormState.source)

        # Переход к следующему шагу
        kb = FormKB.source_keyboard()
        photo = PhotoBank.get_file('SLIDE4')
        await message.answer_photo(photo=photo, caption=self.text_source, reply_markup=kb)


    async def get_source(self, call: CallbackQuery, callback_data: SourceCallback, state: FSMContext):
        await call.message.delete()

        source = callback_data.value
        await state.update_data(source=source)
        data = await state.get_data()

        await state.set_state(FormState.confirm)

        text = self.text_finish["user_confirm"].format(**data, user_id=call.from_user.id)
        step = 'source'
        kb = FormKB.finish_keyboard(to_step=step)
        # photo = PhotoBank.get_file('SLIDE4')
        await call.message.answer(text=text, reply_markup=kb, parse_mode="HTML")


    async def go_back(self, call: CallbackQuery, callback_data: FormBackCallback, state: FSMContext):
        step = callback_data.step

        if step == "name":
            await state.set_state(FormState.name)
            await call.message.delete()

            photo = PhotoBank.get_file('SLIDE1')
            await call.message.answer_photo(photo=photo, caption=self.text_name)

        elif step == "surname":
            await state.set_state(FormState.surname)
            await call.message.delete()

            step = "name"
            kb = FormKB.back_keyboard(to_step=step)
            photo = PhotoBank.get_file('SLIDE2')
            await call.message.answer_photo(photo=photo, caption=self.text_surname, reply_markup=kb)
        
        elif step == "phone":
            await state.set_state(FormState.phone)
            await call.message.delete()

            step = "surname"               
            kb = FormKB.contact_keyboard()
            photo = PhotoBank.get_file('SLIDE3')
            await call.message.answer_photo(photo=photo, caption=self.text_phone, reply_markup=kb)

        elif step == "source":
            await state.set_state(FormState.source)
            await call.message.delete()

            step = "phone"            
            kb = FormKB.source_keyboard()
            photo = PhotoBank.get_file('SLIDE4')
            await call.message.answer_photo(photo=photo, caption=self.text_source, reply_markup=kb)


    async def confirm_form(self, call: CallbackQuery, state: FSMContext):
        data = await state.get_data()
        user_id = call.from_user.id

        req_db = RequestsDB(conn=self.conn)
        await req_db.init()  # на всякий
        request_id = await req_db.create_request(user_id=user_id, data=data)

        text = self.text_finish["admin_form"].format(**data, user_id=call.from_user.id, request_id=request_id)
        if data.get("referrer_id"):
            text += f"\n👥 Реферер: <code>{data['referrer_id']}</code>"
        kb = RequestsKB.decision_keyboard(request_id)
        await call.bot.send_message(chat_id=config.ADMIN_FORM_CHAT_ID, text=text, parse_mode="HTML", reply_markup=kb)

        await call.message.delete()
        await call.message.answer(text=self.text_answer_finish)

        await state.clear()

    # ---------------------------- ДОПОЛНИТЕЛЬНОЕ ----------------------------

    def text_preparation(self):
        self.text_name = (
            f'<b>Добро пожаловать в {config.SHOP_NAME}!</b>\n\n'
            '<b>Введите ваше имя</b>\n'
            '<blockquote>В случае указания недостоверной информации заявка будет отклонена</blockquote>'
        )
        self.text_surname = (
            '<b>Введите вашу фамилию</b>\n'
            '<blockquote>В случае указания недостоверной информации заявка будет отклонена</blockquote>'
        )
        self.text_phone = "<b>Поделитесь контактом, чтобы мы могли получить ваш номер телефона:</b>"
        self.text_source = (
            '<b>Откуда вы узнали о нас?</b>\n'
            '<blockquote>Мы собираем эту информацию для дальнейшего продвижения</blockquote>'
        )

        self.text_finish = {
            "admin_form": (
                "📥 <b>Новая заявка</b>\n\n"
                "👤 Имя: <code>{name}</code>\n"
                "👤 Фамилия: <code>{surname}</code>\n"
                "📞 Телефон: <code>{phone}</code>\n"
                "📡 Источник: <code>{source}</code>\n"
                "🆔 Telegram ID: <code>{user_id}</code>\n"
                "🧾 Request ID: <code>{request_id}</code>"
            ),
            "user_confirm": (
                "<b>Проверьте данные:</b>\n"
                "👤 <code>{name} {surname}</code>\n"
                "📞 Телефон: <code>{phone}</code>\n"
                "📡 Источник: <code>{source}</code>"
            )
        }

        self.text_answer_finish = "✅ Заявка отправлена. Ожидайте ответа."
