from io import BytesIO
import os
import tempfile
from typing import Dict
from aiogram import types, Router
from aiogram import F
from keyboards import AdminFlowCallback
from app.handlers.services.pdf_export import PDFExportService


class AdminExports:
    """
    Экспорт PDF из админки.
    """
    def __init__(self, *, router: Router, cargo):
        self.router = router
        self.cargo = cargo

        self.router.callback_query.register(self.export_admin_pdf, AdminFlowCallback.filter(F.action == "export_admin_pdf"))
        self.router.callback_query.register(self.export_items_pdf, AdminFlowCallback.filter(F.action == "export_items_pdf"))

    async def export_admin_pdf(self, call: types.CallbackQuery, callback_data: AdminFlowCallback):
        cargo_id = callback_data.id
        settle = await self.cargo.settlement_by_cargo(cargo_id=cargo_id)

        tmpdir = tempfile.gettempdir()
        file_path = os.path.join(tmpdir, f"cargo_{cargo_id}_admin.pdf")

        pdf = PDFExportService()
        pdf.generate_admin_cargo_pdf(
            file_path=file_path,
            cargo=settle["cargo"],
            per_user_rows=settle["users"],
            legs=settle["legs"],
        )

        file = types.FSInputFile(file_path)
        text = "📄 Админ-отчёт по посылке"
        await call.message.answer_document(document=file, caption=text)

    async def export_items_pdf(self, call: types.CallbackQuery, callback_data: AdminFlowCallback):
        cargo_id = callback_data.id
        cargo = await self.cargo.cargos.get(cargo_id=cargo_id)
        items = await self.cargo.cargo_items_with_owner(cargo_id=cargo_id)

        tmpdir = tempfile.gettempdir()
        file_path = os.path.join(tmpdir, f"cargo_{cargo_id}_items.pdf")

        photos = await self._collect_item_photos(bot=call.bot, items=items)

        pdf = PDFExportService()
        pdf.generate_cargo_items_pdf(
            file_path=file_path,
            cargo=cargo,
            items=items,
            photos=photos,  # без фоток; если нужно — можно заюзать collect из AdminShipments
        )

        file = types.FSInputFile(file_path)
        text = "🧾 Экспорт всех товаров"
        await call.message.answer_document(document=file, caption=text)


    async def _collect_item_photos(self, *, bot, items: list[dict]) -> Dict[int, bytes]:
        """
        Возвращает {item_id: image_bytes} для тех, где есть photo_file_id.
        """
        result: Dict[int, bytes] = {}
        for it in items:
            file_id = it.get("photo_file_id")
            if not file_id:
                continue
            try:
                file = await bot.get_file(file_id)  # aiogram 3.x
                buf = BytesIO()
                await bot.download_file(file.file_path, buf)
                result[it["id"]] = buf.getvalue()
            except Exception:
                # пропускаем, если файл не доступен
                pass
        return result