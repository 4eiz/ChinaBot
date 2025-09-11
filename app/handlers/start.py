from aiogram import Router
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.filters import CommandStart

from database import UsersDB, RequestsDB

from app.handlers.form.fsm import FormState
from app.handlers import FormClientHandler
from media import PhotoBank
import config



class StartHandler:
    def __init__(self):
        self.users = UsersDB(config.CONNECTION_DATABASE)
        self.router = Router()
        self.router.message.register(self.start, CommandStart())

    async def start(self, message: Message, state: FSMContext):
        await message.delete()
        
        user_id = message.from_user.id
        user = await self.users.get_user(user_id=user_id)

        if user is None:

            req_db = RequestsDB(conn=config.CONNECTION_DATABASE)
            await req_db.init()  # если не инициализировано

            if await req_db.has_active_request(user_id):
                # уже есть активная заявка — нельзя отправлять новую
                status = await req_db.get_last_request_status(user_id)  # для инфы
                text = (
                    f"⏳ У вас уже есть заявка со статусом: <b>{status}</b>.\n"
                    f"Пожалуйста, дождитесь решения."
                )
                await message.answer(text=text, parse_mode="HTML")
                return

            # Новенький — запускаем анкету
            await state.set_state(FormState.name)
            form = FormClientHandler(conn=config.CONNECTION_DATABASE)
            photo = PhotoBank.get_file('SLIDE1')
            await message.answer_photo(photo=photo, caption=form.text_name)
        else:
            text = f"Добро пожаловать в {config.SHOP_NAME}!"
            await message.answer(text=text)
