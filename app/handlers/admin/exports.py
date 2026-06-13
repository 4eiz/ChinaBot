from io import BytesIO
import os
import tempfile
from typing import Dict

from aiogram import types, Router, F

from keyboards import AdminFlowCallback
from database import CargoService
from app.handlers.services.pdf_export import PDFExportService
from app.handlers.services.shipment_exporter import (
    export_cn_msk_goods,
    export_text_form,
    export_expedition,
)


class AdminExports:
    """
    Экспорт документов (PDF / Excel) из панели администратора.
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
        self.router.callback_query.register(
            self.export_excel_352,
            AdminFlowCallback.filter(F.action == "export_excel_352")
        )
        self.router.callback_query.register(
            self.export_excel_sadovod,
            AdminFlowCallback.filter(F.action == "export_excel_sadovod")
        )
        self.router.callback_query.register(
            self.export_excel_expedition,
            AdminFlowCallback.filter(F.action == "export_excel_expedition")
        )

    # ------------------------------------------------------------------
    # PDF
    # ------------------------------------------------------------------

    async def export_admin_pdf(
        self, call: types.CallbackQuery, callback_data: AdminFlowCallback
    ) -> None:
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
        await call.message.answer_document(
            document=file, caption="📄 Админ-отчёт по посылке"
        )

    async def export_items_pdf(
        self, call: types.CallbackQuery, callback_data: AdminFlowCallback
    ) -> None:
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
        await call.message.answer_document(
            document=file, caption="🧾 Экспорт всех товаров"
        )

    # ------------------------------------------------------------------
    # Excel
    # ------------------------------------------------------------------

    async def export_excel_352(
        self, call: types.CallbackQuery, callback_data: AdminFlowCallback
    ) -> None:
        """Excel 352 — CN→MSK, лист «Товары» с фото."""
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
        await call.message.answer_document(
            document=file,
            caption=f"📊 Excel 352 по посылке #{cargo_id}",
        )

    async def export_excel_sadovod(
        self, call: types.CallbackQuery, callback_data: AdminFlowCallback
    ) -> None:
        """Excel Садовод — текстовый бланк без фото."""
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
        await call.message.answer_document(
            document=file,
            caption=f"📊 Excel Садовод по посылке #{cargo_id}",
        )

    async def export_excel_expedition(
        self, call: types.CallbackQuery, callback_data: AdminFlowCallback
    ) -> None:
        """
        Excel ТК Экспедиция — Южные ворота.

        Бот считает количество товаров и автоматически выбирает
        нужный лист шаблона:
          1–31   → лист «1-31»
          32–83  → лист «32-83»
          84–134 → лист «84-134»
          135–185 → лист «135-185»

        Единица измерения — всегда «шт.»
        Стоимость: price_usd × usd_to_byn × qty  (1 USD = 2.9 BYN по умолчанию)
        """
        cargo_id = callback_data.id

        try:
            file_path = await export_expedition(
                cargo_service=self.cargo,
                cargo_id=cargo_id,
            )
        except FileNotFoundError:
            await call.answer(
                "❌ Шаблон ТК Экспедиция не найден.\n"
                "Положите файл в media/excel/expedition.xlsx",
                show_alert=True,
            )
            return
        except RuntimeError as exc:
            await call.answer(f"⚠️ {exc}", show_alert=True)
            return
        except Exception:
            await call.answer(
                "⚠️ Не удалось сформировать Excel ТК Экспедиция",
                show_alert=True,
            )
            return

        file = types.FSInputFile(file_path)
        await call.message.answer_document(
            document=file,
            caption=f"🚛 ТК Экспедиция — посылка #{cargo_id}",
        )

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    async def _collect_item_photos(
        self, *, bot, items: list[dict]
    ) -> Dict[int, bytes]:
        """Возвращает {item_id: image_bytes} для тех, где есть photo_file_id."""
        result: Dict[int, bytes] = {}
        for it in items:
            file_id = it.get("photo_file_id")
            if not file_id:
                continue
            try:
                file = await bot.get_file(file_id)
                buf = BytesIO()
                await bot.download_file(file.file_path, buf)
                result[it["id"]] = buf.getvalue()
            except Exception:
                pass
        return result
