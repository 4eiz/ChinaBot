from io import BytesIO
import os
import tempfile
from typing import Dict

from aiogram import types, Router, F

from keyboards import AdminFlowCallback
from database import CargoService
from app.handlers.services.pdf_export import PDFExportService
from app.handlers.services.shipment_exporter import export_cn_msk_goods, export_text_form


class AdminExports:
    """
    Экспорт PDF из админки.
    """

    def __init__(self, *, router: Router, cargo: CargoService):
        self.router = router
        self.cargo = cargo

        self.router.callback_query.register(
            self.export_admin_pdf,
            AdminFlowCallback.filter(F.action == "export_admin_pdf")
        )
        self.router.callback_query.register(
            self.export_items_pdf,
            AdminFlowCallback.filter(F.action == "export_items_pdf")
        )

        # 🔹 Новые Excel-экспорты
        self.router.callback_query.register(
            self.export_excel_352,
            AdminFlowCallback.filter(F.action == "export_excel_352")
        )
        self.router.callback_query.register(
            self.export_excel_sadovod,
            AdminFlowCallback.filter(F.action == "export_excel_sadovod")
        )


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

        payload = await self.cargo.get_admin_items_export_payload(cargo_id=cargo_id)
        if not payload:
            await call.answer("❌ Посылка не найдена", show_alert=True)
            return

        cargo = payload["cargo"]
        items = payload["items"]

        tmpdir = tempfile.gettempdir()
        file_path = os.path.join(tmpdir, f"cargo_{cargo_id}_items.pdf")

        photos = await self._collect_item_photos(bot=call.bot, items=items)

        pdf = PDFExportService()
        pdf.generate_cargo_items_pdf(
            file_path=file_path,
            cargo=cargo,
            items=items,
            photos=photos,
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
    

    async def export_excel_352(self, call: types.CallbackQuery, callback_data: AdminFlowCallback):
        """
        Excel 352 — CN→MSK, лист «Товары» с фото.
        """
        cargo_id = callback_data.id

        try:
            file_path = await export_cn_msk_goods(
                bot=call.bot,
                cargo_service=self.cargo,
                cargo_id=cargo_id,
            )
        except FileNotFoundError:
            await call.answer("❌ Excel-шаблон для 352 не найден", show_alert=True)
            return
        except Exception:
            await call.answer("⚠️ Не удалось сформировать Excel 352", show_alert=True)
            return

        file = types.FSInputFile(file_path)
        caption = f"📊 Excel 352 по посылке #{cargo_id}"
        await call.message.answer_document(document=file, caption=caption)

    async def export_excel_sadovod(self, call: types.CallbackQuery, callback_data: AdminFlowCallback):
        """
        Excel Садовод — текстовый бланк без фото.
        """
        cargo_id = callback_data.id

        try:
            file_path = await export_text_form(
                cargo_service=self.cargo,
                cargo_id=cargo_id,
            )
        except FileNotFoundError:
            await call.answer("❌ Excel-шаблон для Садовода не найден", show_alert=True)
            return
        except Exception:
            await call.answer("⚠️ Не удалось сформировать Excel Садовод", show_alert=True)
            return

        file = types.FSInputFile(file_path)
        caption = f"📊 Excel Садовод по посылке #{cargo_id}"
        await call.message.answer_document(document=file, caption=caption)
