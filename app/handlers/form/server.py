import json

from aiogram import Router
from aiogram import F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext

from keyboards.callback_data import RequestActionCallback
from database import RequestsDB, UsersDB

class FormServerHandler:
    def __init__(self, conn, admin_chat_id: int):
        self.router = Router()
        self.admin_chat_id = admin_chat_id
        self.requests = RequestsDB(conn)
        self.user_db = UsersDB(conn)

        self.router.callback_query.register(
            self.on_decision,
            RequestActionCallback.filter()
        )

    async def on_decision(self, call: CallbackQuery, callback_data: RequestActionCallback, state: FSMContext):
        action = callback_data.action   # 'approve' | 'reject'
        request_id = int(callback_data.request_id)

        req = await self.requests.get_request(request_id)
        if not req:
            text = "Заявка не найдена"
            await call.answer(text=text, show_alert=True)
            return

        user_id = req["user_id"]
        old = "📥 Новая заявка"

        if action == "approve":
            await self.requests.update_status(request_id, "approved")
            
            data = req.get("data") or {}
            if isinstance(data, str):
                try:
                    data = json.loads(data)
                except json.JSONDecodeError:
                    data = {}

            user_fields = self.__map_request_data_to_user_fields(user_id=user_id, data=data)

            try:
                await self.user_db.add_user(**user_fields)
            except Exception as e:
                # можно логировать
                await call.answer("Ошибка при сохранении пользователя", show_alert=True)
                return
            
            # редактируем админское сообщение
            admin_id = call.from_user.id
            text = call.message.html_text
            text = f"✅ Заявка <code>#{request_id}</code> принята\nАдмин: <code>{admin_id}</code>" + text.replace(old, '')
            try:
                await call.message.edit_text(
                    text=text,
                    parse_mode="HTML"
                )
            except:
                pass

            # уведомляем пользователя
            try:
                text = "<b>✅ Ваша заявка одобрена. Пропишите команду /start</b>"
                await call.bot.send_message(
                    chat_id=user_id,
                    text=text,
                    parse_mode='HTML'
                )
            except:
                pass

            text = "Заявка принята"
            await call.answer(text=text)

        elif action == "reject":
            await self.requests.update_status(request_id, "rejected")
            text = call.message.html_text
            admin_id = call.from_user.id
            text = f"<b>❌ Заявка <code>#{request_id}</code> ОТКЛОНЕНА\n\Админ: <code>{user_id}</code>" + text.replace(old, '')
            try:
                await call.message.edit_text(
                    text=text,
                    parse_mode="HTML"
                )
            except:
                pass
            try:
                text = "<b>❌ Ваша заявка отклонена. Вы можете отправить новую, исправив данные.</b>"
                await call.bot.send_message(
                    chat_id=user_id,
                    text=text,
                    parse_mode='HTML'
                )
            except:
                pass
            text = "Заявка отклонена"
            await call.answer(text=text)

        else:
            text = "Неизвестное действие"
            await call.answer(text=text)


    def __map_request_data_to_user_fields(self, user_id: int, data: dict) -> dict:
        """
        Переносит поля анкеты в поля таблицы users.
        Подстрой под свои реальные ключи из FSM. Ниже пример:
        - name        <- data['full_name']  (если у тебя именно такое имя поля)
        - surname     <- data['surname']
        - phone_number<- data['phone']
        - source      <- data['source']     (код или человекочитаемое)
        """
        name = data.get("full_name") or data.get("name") or ""
        surname = data.get("surname") or ""
        phone = data.get("phone") or ""
        source = data.get("source") or ""

        # Можно добавить другие поля, если есть (balance, rate и т.п.)
        fields = {
            "id": user_id,                 # обязателен, PK в твоей схеме
            "name": name,
            "surname": surname,
            "phone_number": phone,
            "source": source,
            # "balance": 0,                # не обязательно, у тебя DEFAULT 0
            # "rate": 0.1822,              # если нужно переопределять дефолт
        }
        # Удалим пустые ключи, если не хочешь писать пустые строки
        return {k: v for k, v in fields.items() if v is not None}