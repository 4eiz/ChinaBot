from aiogram import Router

import config
from app.handlers import *
from app.handlers.admin import setup_admin_handlers



def get_routers() -> list[Router]:
    admin_router = setup_admin_handlers(conn=config.CONNECTION_DATABASE)

    return [
        StartHandler().router,
        FormClientHandler(conn=config.CONNECTION_DATABASE).router,
        FormServerHandler(conn=config.CONNECTION_DATABASE, admin_chat_id=config.ADMIN_FORM_CHAT_ID).router,
        OCRHandler(bot=config.bot, conn=config.CONNECTION_DATABASE).router,
        ProfileHandler(conn=config.CONNECTION_DATABASE).router,
        ShipmentsHandler(conn=config.CONNECTION_DATABASE).router,
        # AdminHandler(conn=config.CONNECTION_DATABASE).router,
        admin_router,
    ]