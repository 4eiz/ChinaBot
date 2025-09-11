from aiogram import Router
from config import bot, ADMIN_CHAT_ID
from database import CargoService, CargoPaymentsDB, UsersDB

from app.handlers.services.admin_notifier import AdminNotifier
from app.handlers.services.user_notifier import UserNotifier

from .shipments import AdminShipments
from .payments import AdminPayments
from .exports import AdminExports


def setup_admin_handlers(conn) -> Router:
    """
    Создаёт общий Router админки и подключает подмодули.
    """
    router = Router()

    # Сервисы (одни и те же для всех подмодулей)
    cargo = CargoService(conn=conn)
    pay = CargoPaymentsDB(conn=conn)
    users = UsersDB(conn=conn)
    notifier = AdminNotifier(bot=bot, admin_chat_id=ADMIN_CHAT_ID)
    user_notifier = UserNotifier(bot=bot)

    # Модули
    AdminShipments(router=router, cargo=cargo, users=users, notifier=notifier, user_notifier=user_notifier)
    AdminPayments(router=router, cargo=cargo, pay=pay, users=users)
    AdminExports(router=router, cargo=cargo)

    return router
