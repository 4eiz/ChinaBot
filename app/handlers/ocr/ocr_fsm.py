from aiogram.fsm.state import State, StatesGroup

class OCRState(StatesGroup):
    editing = State()
    awaiting_value = State()

    waiting_instruction = State()
    awaiting_product_photo = State()

    awaiting_title = State()          # уже было
    awaiting_link = State()           # ← новое: ждём URL
    choosing_type = State()           # ← новое: выбор типа товара
    choosing_scope = State()          # ← новое: выбор общая/личная
    choosing_personal_cargo = State() # ← новое: выбор личной посылки

    final_confirm = State()
