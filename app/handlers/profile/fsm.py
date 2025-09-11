from aiogram.fsm.state import StatesGroup, State


class ShipmentFSM(StatesGroup):
    type = State()
    name = State()
    confirm = State()
