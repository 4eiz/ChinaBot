from aiogram.fsm.state import StatesGroup, State

class FormState(StatesGroup):
    name = State()
    surname = State()
    phone = State()
    source = State()
    confirm = State()
