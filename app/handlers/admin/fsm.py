from aiogram.fsm.state import StatesGroup, State



class PaymentForm(StatesGroup):
    kind = State()      # goods_cny | delivery_msk | delivery_by | advance | refund | other
    amount = State()
    note = State()
