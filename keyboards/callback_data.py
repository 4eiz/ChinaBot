from aiogram.filters.callback_data import CallbackData



# --------------------- client.py ---------------------

class MenuCallback(CallbackData, prefix="menu"):
    action: str

# --------------------- form.py ---------------------

class SourceCallback(CallbackData, prefix="source"):
    value: str

class FormBackCallback(CallbackData, prefix="form_back"):
    step: str

class ConfirmCallback(CallbackData, prefix="confirm"):
    action: str  # например: "yes", "no"

class RequestActionCallback(CallbackData, prefix="req"):
    action: str          # 'approve' | 'reject' | 'cancel' (если надо)
    request_id: int

# --------------------- ocr.py ---------------------

class OCRFlowCallback(CallbackData, prefix="ocr_flow"):
    action: str  # "confirm" | "change_photo" | "restart"

# редактирование конкретного поля
class OCREditFieldCallback(CallbackData, prefix="ocr_edit"):
    field: str  # price|color|size|quantity|title

class OCRTypeCallback(CallbackData, prefix="ocrtype"):
    code: str  # 'clothes'|'shoes'|'household'

class OCRScopeCallback(CallbackData, prefix="ocrscope"):
    scope: str  # 'shared'|'personal'

class OCRPersonalCargoCallback(CallbackData, prefix="ocrcargo"):
    cargo_id: int

# --------------------- profile.py ---------------------

class ProfileFlowCallback(CallbackData, prefix="profile"):
    action: str

class ShipmentFlowCallback(CallbackData, prefix="shipment"):
    action: str
    id: int | None = None
    item_id: int | None = None
    cargo_type: str | None = None
    page: int | None = None

# --------------------- admin.py ---------------------

class ShipmentFlowCallback(CallbackData, prefix="shipment"):
    action: str
    id: int | None = None
    item_id: int | None = None
    cargo_type: str | None = None
    page: int | None = None

class AdminFlowCallback(CallbackData, prefix="admin"):
    action: str
    status: str | None = None       # cargo_id
    id: int | None = None       # cargo_id
    user_id: int | None = None  # для платежей/сводок

class PaymentFlowCallback(CallbackData, prefix="payment"):
    action: str
    amount: float
