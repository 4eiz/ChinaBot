import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

os.environ.setdefault('BOT_TOKEN', '123456:TEST_TOKEN_FOR_OFFLINE_TESTS')

from aiogram import Bot, Dispatcher, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import DeleteMessage, SendMessage
from aiogram.types import Update
from app.utils.expired_message import ExpiredMessageMiddleware
from app.utils import safe_delete


class ExpiredMessageTests(unittest.IsolatedAsyncioTestCase):
    async def run_update(self, error=None, use_safe_delete=False, admin=False):
        bot = Bot(os.environ['BOT_TOKEN'])
        bot.send_photo = AsyncMock()
        dp = Dispatcher()
        dp.update.outer_middleware(ExpiredMessageMiddleware())
        router = Router()
        completed = AsyncMock()

        @router.callback_query()
        async def handle(call, state):
            await state.set_state('ordering')
            if use_safe_delete:
                await safe_delete(call.message)
            elif error:
                raise error
            await completed()

        dp.include_router(router)
        update = Update.model_validate({
            'update_id': 1,
            'callback_query': {
                'id': 'test', 'chat_instance': 'test', 'data': 'test',
                'from': {'id': 42, 'is_bot': False, 'first_name': 'Client'},
                'message': {'message_id': 1, 'date': 1,
                            'chat': {'id': 42, 'type': 'private'}},
            },
        })
        users = SimpleNamespace(is_admin=AsyncMock(return_value=admin))
        with patch('app.utils.expired_message.UsersDB', return_value=users), \
             patch('app.utils.expired_message.PhotoBank.get_file', return_value='photo'), \
             patch('aiogram.types.CallbackQuery.answer', new=AsyncMock()), \
             patch('aiogram.types.Message.delete', new=AsyncMock(side_effect=error)):
            try:
                await dp.feed_update(bot, update)
                state = dp.fsm.get_context(bot=bot, chat_id=42, user_id=42)
                return bot.send_photo, completed, await state.get_state()
            finally:
                await dp.storage.close()
                await bot.session.close()

    async def test_old_message_sends_menu_and_clears_state(self):
        error = TelegramBadRequest(DeleteMessage(chat_id=42, message_id=1), "message can't be deleted for everyone")
        sent, completed, state = await self.run_update(error)
        sent.assert_awaited_once()
        completed.assert_not_awaited()
        self.assertIsNone(state)
        self.assertIn('Профиль', str(sent.call_args.kwargs['reply_markup']))

    async def test_missing_message_through_safe_delete(self):
        error = TelegramBadRequest(DeleteMessage(chat_id=42, message_id=1), 'message to delete not found')
        sent, completed, state = await self.run_update(error, use_safe_delete=True)
        sent.assert_awaited_once()
        completed.assert_not_awaited()
        self.assertIsNone(state)

    async def test_success_continues_handler(self):
        sent, completed, state = await self.run_update()
        sent.assert_not_awaited()
        completed.assert_awaited_once()
        self.assertEqual(state, 'ordering')

    async def test_admin_menu(self):
        error = TelegramBadRequest(DeleteMessage(chat_id=42, message_id=1), "message can't be deleted")
        sent, _, _ = await self.run_update(error, admin=True)
        self.assertIn('Админ-панель', str(sent.call_args.kwargs['reply_markup']))

    async def test_unrelated_error_propagates(self):
        error = TelegramBadRequest(DeleteMessage(chat_id=42, message_id=1), 'chat not found')
        with self.assertRaises(TelegramBadRequest):
            await self.run_update(error)

    async def test_other_method_error_propagates(self):
        error = TelegramBadRequest(SendMessage(chat_id=42, text='test'), "message can't be deleted")
        with self.assertRaises(TelegramBadRequest):
            await self.run_update(error)
