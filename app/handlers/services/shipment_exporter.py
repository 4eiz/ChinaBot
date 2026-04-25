# app/handlers/services/shipment_exporter.py
import os
import io
import json
import copy
import tempfile
from datetime import datetime
from decimal import Decimal
from typing import Optional, List, Tuple, Dict

import asyncio
from aiogram import Bot
from openpyxl import load_workbook
from openpyxl.drawing.image import Image as XLImage
from openpyxl.drawing.spreadsheet_drawing import AnchorMarker, OneCellAnchor, XDRPositiveSize2D
from openpyxl.utils import column_index_from_string, get_column_letter
from openpyxl.worksheet.worksheet import Worksheet
from PIL import Image as PILImage


# ============================================================
# 1) CN→MSK экспорт (лист «Товары», с ФОТО)
# ============================================================

class ExcelExportService:
    """
    Экспорт посылки в Excel (лист «Товары», Китай→Москва, С ФОТО).

    - Заполнение со 2-й строки.
    - Фото берём по Telegram file_id, вписываем в реальную ячейку E{row} БЕЗ изменения
      высоты строки/ширины колонки, с небольшим внутренним отступом.
    - «цвет строго» (столбец 19 / S) — всегда 'да'.
    - «Цена доставки» (15 / O) — не трогаем.
    - «Цена (Юани)» (16 / P) — формула шаблона остаётся.
    - Возвращаем путь к временному xlsx: cargo_<ID>_<YYYYMMDD>.xlsx — отправляешь уже в своём месте.
    """

    PHOTO_COL_LETTER = "E"
    # Индексы колонок соответствуют шаблону cargo.xlsx (заголовки в файле).
    #
    # A  1  — №
    # C  3  — Наименование
    # D  4  — Ссылка
    # E  5  — Фото
    # F  6  — Цвет
    # G  7  — Материал
    # H  8  — «中文品名» / Китайское наименование
    # I  9  — Бренд
    # J 10  — Размер
    # K 11  — Примечания
    # M 13  — Кол-во
    # N 14  — Цена за 1 ед. (¥)
    # S 19  — цвет строго
    COL_INDEX = {
        "num":          1,   # A
        "title":        3,   # C
        "link":         4,   # D
        "color":        6,   # F
        "material":     7,   # G
        "cn_title":     8,   # H
        "brand":        9,   # I
        "size":         10,  # J
        "notes":        11,  # K
        "qty":          13,  # M
        "unit_price":   14,  # N
        "strict_color": 19,  # S
    }

    def __init__(
        self,
        *,
        bot: Bot,
        template_path: Optional[str] = None,
        max_concurrency: int = 8,
        photo_inner_padding_px: int = 6,
    ) -> None:
        """
        :param bot: aiogram Bot — для скачивания фото по file_id
        :param template_path: путь к Excel-шаблону; по умолчанию: env CARGO_XLSX_TEMPLATE или media/cargo.xlsx
        :param max_concurrency: параллельность скачивания фото
        :param photo_inner_padding_px: отступ внутри клетки (px) — чтобы фото было чуть меньше рамки
        """
        self.bot = bot
        self.template_path = (
            template_path
            or os.getenv("CARGO_XLSX_TEMPLATE")
            or os.path.join("media", "excel", "cargo.xlsx")
        )
        self.sema = asyncio.Semaphore(int(max_concurrency))
        self.photo_inner_padding_px = int(photo_inner_padding_px)

    # ---------- helpers: размеры, загрузка, подготовка изображений ----------

    @staticmethod
    async def _notes_from_extra(extra: object) -> str:
        """ Оставляем только «человеческие» примечания, без JSON-шума. """
        KEYS = ("note", "comment", "备注", "примечание", "notes")
        if extra is None:
            return ""
        if isinstance(extra, dict):
            for k in KEYS:
                v = extra.get(k)
                if v:
                    return str(v)
            return ""
        if isinstance(extra, str):
            try:
                data = json.loads(extra)
                if isinstance(data, dict):
                    for k in KEYS:
                        v = data.get(k)
                        if v:
                            return str(v)
            except Exception:
                pass
        return ""

    @staticmethod
    async def _extra_field(extra: object, keys: Tuple[str, ...]) -> str:
        """Достаём значение из extra (dict или JSON-строка) по списку ключей."""
        if extra is None:
            return ""
        if isinstance(extra, dict):
            for k in keys:
                v = extra.get(k)
                if v not in (None, ""):
                    return str(v)
            return ""
        if isinstance(extra, str):
            try:
                data = json.loads(extra)
                if isinstance(data, dict):
                    for k in keys:
                        v = data.get(k)
                        if v not in (None, ""):
                            return str(v)
            except Exception:
                pass
        return ""

    @staticmethod
    async def _points_to_pixels(points: float) -> float:
        return points * 4.0 / 3.0  # 1pt ~ 1.3333 px

    @staticmethod
    async def _col_width_chars_to_pixels(chars_width: float) -> float:
        return chars_width * 7.0  # грубое, но устойчивое приближение

    @staticmethod
    async def _worksheet_default_row_height_pt(ws: Worksheet) -> float:
        return float(getattr(ws.sheet_format, "defaultRowHeight", 15.0) or 15.0)

    @staticmethod
    async def _worksheet_default_col_width_chars(ws: Worksheet) -> float:
        return float(getattr(ws.sheet_format, "defaultColWidth", 8.43) or 8.43)

    async def _get_cell_box_pixels(self, ws: Worksheet, row: int, col_letter: str) -> Tuple[int, int]:
        """ Возвращает фактический размер ячейки (ширина/высота) в пикселях. Ничего не меняем в листе. """
        # width
        col_dim = ws.column_dimensions.get(col_letter)
        if col_dim and col_dim.width:
            col_chars = float(col_dim.width)
        else:
            col_chars = await self._worksheet_default_col_width_chars(ws)
        width_px = await self._col_width_chars_to_pixels(col_chars)
        # height
        row_dim = ws.row_dimensions.get(row)
        if row_dim and row_dim.height:
            row_pt = float(row_dim.height)
        else:
            row_pt = await self._worksheet_default_row_height_pt(ws)
        height_px = await self._points_to_pixels(row_pt)
        return int(width_px), int(height_px)

    async def _download_photo_bytes(self, file_id: Optional[str]) -> Optional[bytes]:
        """ Скачивает файл из Telegram по file_id. Возвращает bytes или None. """
        if not file_id:
            return None
        async with self.sema:
            try:
                tg_file = await self.bot.get_file(file_id)
                buf = io.BytesIO()
                await self.bot.download(tg_file, destination=buf)
                return buf.getvalue()
            except Exception:
                return None

    async def _process_image_to_png_fit_box(
        self,
        raw: bytes,
        box_w_px: int,
        box_h_px: int,
        padding_px: int,
    ) -> Optional[Tuple[bytes, int, int]]:
        """
        Вписывает изображение в бокс ячейки (минус паддинги), без изменения пропорций.
        Возвращает PNG-байты и фактический (w,h) в пикселях.
        """
        def _work() -> Optional[Tuple[bytes, int, int]]:
            try:
                img = PILImage.open(io.BytesIO(raw)).convert("RGB")
                w, h = img.size
                tgt_w = max(1, box_w_px - 2 * padding_px)
                tgt_h = max(1, box_h_px - 2 * padding_px)
                scale = min(tgt_w / max(1, w), tgt_h / max(1, h))
                new_w = max(1, int(w * scale))
                new_h = max(1, int(h * scale))
                if scale < 1.0:
                    img = img.resize((new_w, new_h), PILImage.LANCZOS)
                out = io.BytesIO()
                img.save(out, format="PNG", optimize=True)
                return out.getvalue(), new_w, new_h
            except Exception:
                return None
        return await asyncio.to_thread(_work)

    # ---------- публичный метод ----------

    async def generate_goods_sheet(self, *, cargo_service, cargo_id: int) -> str:
        """
        Генерирует Excel по шаблону «Товары» для CN→MSK, возвращает путь к временному файлу.

        :param cargo_service: твой CargoService (async), должен уметь: items.list_by_cargo(cargo_id)
        :param cargo_id: ID посылки
        :return: str — /tmp/cargo_<ID>_<YYYYMMDD>.xlsx
        """
        # товары
        items: List[dict] = await cargo_service.items.list_by_cargo(cargo_id=cargo_id)
        file_ids = [it.get("photo_file_id") for it in items]

        # фото параллельно
        photos_raw = await asyncio.gather(*[self._download_photo_bytes(fid) for fid in file_ids])

        # шаблон
        if not os.path.exists(self.template_path):
            raise FileNotFoundError(f"Excel-шаблон не найден: {self.template_path}")
        wb = load_workbook(self.template_path)
        ws = wb["Товары"] if "Товары" in wb.sheetnames else wb.active

        # заполнение
        row = 2
        cell = ws.cell
        for i, it in enumerate(items, 1):
            title = it.get("title") or "Без названия"
            link = it.get("source_url") or ""
            color = it.get("color") or ""
            size = it.get("size") or ""
            qty = int(it.get("quantity") or 0)
            price = it.get("price") or 0
            notes = await self._notes_from_extra(it.get("extra"))

            # Доп. поля из extra
            extra = it.get("extra")
            material = await self._extra_field(extra, ("material", "материал", "Материал", "材质"))
            cn_title = await self._extra_field(extra, (
                "cn_title", "chinese_name", "chinese_title", "中文品名", "中文名称", "名称"
            ))
            brand = await self._extra_field(extra, ("brand", "бренд", "Бренд", "品牌"))

            cell(row=row, column=self.COL_INDEX["num"],          value=i)
            cell(row=row, column=self.COL_INDEX["title"],        value=str(title))
            cell(row=row, column=self.COL_INDEX["link"],         value=str(link))
            cell(row=row, column=self.COL_INDEX["color"],        value=str(color))
            cell(row=row, column=self.COL_INDEX["material"],     value=str(material))
            cell(row=row, column=self.COL_INDEX["cn_title"],     value=str(cn_title))
            cell(row=row, column=self.COL_INDEX["brand"],        value=str(brand))
            cell(row=row, column=self.COL_INDEX["size"],         value=str(size))
            cell(row=row, column=self.COL_INDEX["notes"],        value=str(notes))
            cell(row=row, column=self.COL_INDEX["qty"],          value=qty)
            try:
                unit_price = float(Decimal(str(price)))
            except Exception:
                unit_price = 0.0
            cell(row=row, column=self.COL_INDEX["unit_price"],   value=unit_price)
            cell(row=row, column=self.COL_INDEX["strict_color"], value="да")  # цвет строго

            # фото: вписываем по центру клетки
            raw = photos_raw[i - 1]
            if raw:
                box_w_px, box_h_px = await self._get_cell_box_pixels(ws, row=row, col_letter=self.PHOTO_COL_LETTER)
                processed = await self._process_image_to_png_fit_box(
                    raw=raw,
                    box_w_px=box_w_px,
                    box_h_px=box_h_px,
                    padding_px=self.photo_inner_padding_px,
                )
                if processed:
                    png_bytes, w_px, h_px = processed
                    bio = io.BytesIO(png_bytes)
                    xl_img = XLImage(bio)
                    xl_img.width = w_px
                    xl_img.height = h_px

                    # центрирование в пределах ячейки
                    offset_x = max(0, (box_w_px - w_px) // 2)
                    offset_y = max(0, (box_h_px - h_px) // 2)

                    col_idx_1based = column_index_from_string(self.PHOTO_COL_LETTER)
                    marker = AnchorMarker(
                        col=col_idx_1based - 1,         # zero-based
                        colOff=offset_x * 9525,         # 1 px = 9525 EMUs
                        row=row - 1,                    # zero-based
                        rowOff=offset_y * 9525,
                    )
                    ext = XDRPositiveSize2D(cx=w_px * 9525, cy=h_px * 9525)
                    anchor = OneCellAnchor(_from=marker, ext=ext)
                    ws.add_image(xl_img, anchor)

            row += 1

        # сохранить во временный файл
        today = datetime.now().strftime("%Y%m%d")
        tmpdir = tempfile.gettempdir()
        file_path = os.path.join(tmpdir, f"cargo_{cargo_id}_{today}.xlsx")
        wb.save(file_path)
        wb.close()
        return file_path


# ============================================================
# 2) Текстовый бланк (второй шаблон, БЕЗ фото)
#    — наполнение из БД, без чтения других Excel.
# ============================================================

class ExcelTextFormExportService:
    """
    Экспорт «текстового» бланка (второй шаблон, без фото) из БД.

    - Берём товары из БД и заполняем «кривой» шаблон: копируем формат эталонной строки,
      учитываем мерджи, строку «Всего» переносим вниз.
    - Возвращаем путь к временному файлу cargo_<ID>_<YYYYMMDD>_form.xlsx.
    """

    def __init__(
        self,
        *,
        template_path: Optional[str] = None,
        sheet_name: Optional[str] = None,
        start_row: int = 5,
        end_row: int = 33,
        total_label: str = "Всего",
        yuan_to_rub: Optional[Decimal] = None,
    ) -> None:
        """
        :param template_path: путь к шаблону текстового бланка (обязателен)
        :param sheet_name: имя листа (если None — active)
        :param start_row: первая строка таблицы в шаблоне
        :param end_row: последняя «готовая» строка таблицы в шаблоне
        :param total_label: текст, по которому ищем строку «Всего»
        :param yuan_to_rub: курс CNY→RUB (если None — env YUAN_TO_RUB или 15)
        """
        self.template_path = (
            template_path
            or os.getenv("CARGO_XLSX_TEMPLATE")
            or os.path.join("media", "excel", "sadovod.xlsx")
        )
        if not self.template_path:
            raise ValueError("Не указан template_path и не задан ENV TEXT_FORM_XLSX_TEMPLATE")
        self.sheet_name = sheet_name
        self.start_row = int(start_row)
        self.end_row = int(end_row)
        self.total_label = total_label
        env_rate = os.getenv("YUAN_TO_RUB") or "15"
        self.yuan_to_rub = Decimal(str(yuan_to_rub)) if yuan_to_rub is not None else Decimal(env_rate)
        self._total_row_cache: Dict[int, dict] = {}

        self.column_mapping = {
            "title":       list(range(3,  9)),   # C–H
            "unit":        list(range(12, 14)),  # L–M
            "qty":         list(range(18, 22)),  # R–U
            "unit_price":  list(range(22, 27)),  # V–Z
        }

    # ---------- helpers: стили, мерджи, поиск «Всего», запись в мерджи ----------

    async def _copy_row_format(self, sheet, source_row: int, target_row: int) -> None:
        for col in range(1, sheet.max_column + 1):
            src = sheet.cell(row=source_row, column=col)
            tgt = sheet.cell(row=target_row, column=col)
            if getattr(src, "has_style", False):
                tgt.font = copy.copy(src.font)
                tgt.border = copy.copy(src.border)
                tgt.fill = copy.copy(src.fill)
                tgt.number_format = copy.copy(src.number_format)
                tgt.protection = copy.copy(src.protection)
                tgt.alignment = copy.copy(src.alignment)

    async def _remove_merged_ranges_on_row(self, sheet, row: int) -> None:
        to_remove = [rng for rng in sheet.merged_cells.ranges if rng.min_row == row and rng.max_row == row]
        for rng in to_remove:
            sheet.unmerge_cells(str(rng))

    async def _move_merged_cells(self, sheet, source_row: int, target_row: int) -> None:
        to_copy = [rng for rng in sheet.merged_cells.ranges if rng.min_row == source_row and rng.max_row == source_row]
        for rng in to_copy:
            coord = f"{get_column_letter(rng.min_col)}{target_row}:{get_column_letter(rng.max_col)}{target_row}"
            sheet.merge_cells(coord)

    async def _find_total_row(self, sheet) -> Optional[int]:
        for row in sheet.iter_rows():
            for cell in row:
                v = cell.value
                if isinstance(v, str) and self.total_label in v:
                    return cell.row
        return None

    async def _cache_total_row(self, sheet, row: int) -> None:
        self._total_row_cache.clear()
        for col in range(1, sheet.max_column + 1):
            c = sheet.cell(row=row, column=col)
            self._total_row_cache[col] = {
                "value": c.value,
                "font": copy.copy(c.font),
                "border": copy.copy(c.border),
                "fill": copy.copy(c.fill),
                "alignment": copy.copy(c.alignment),
                "number_format": c.number_format,
            }
        self._total_row_cache["merges"] = [
            (rng.min_col, rng.max_col)
            for rng in sheet.merged_cells.ranges
            if rng.min_row == row and rng.max_row == row
        ]

    async def _restore_total_row(self, sheet, target_row: int) -> None:
        sheet.insert_rows(target_row)
        for col, data in self._total_row_cache.items():
            if col == "merges":
                continue
            cell = sheet.cell(row=target_row, column=int(col))
            cell.value = data["value"]
            cell.font = copy.copy(data["font"])
            cell.border = copy.copy(data["border"])
            cell.fill = copy.copy(data["fill"])
            cell.alignment = copy.copy(data["alignment"])
            cell.number_format = data["number_format"]
        for min_col, max_col in self._total_row_cache.get("merges", []):
            coord = f"{get_column_letter(min_col)}{target_row}:{get_column_letter(max_col)}{target_row}"
            sheet.merge_cells(coord)

    async def _safe_set_cell(self, sheet, row: int, col: int, value) -> None:
        cell = sheet.cell(row=row, column=col)
        if type(cell).__name__ == "MergedCell":
            for merged in sheet.merged_cells.ranges:
                if cell.coordinate in merged:
                    top_left = sheet.cell(row=merged.min_row, column=merged.min_col)
                    top_left.value = value
                    return
        else:
            cell.value = value

    # ---------- БД → плоские строки ----------

    async def _load_rows_from_db(self, cargo_service, cargo_id: int) -> List[dict]:
        items = await cargo_service.items.list_by_cargo(cargo_id=cargo_id)
        rows: List[dict] = []
        for it in items:
            title = it.get("title") or "Без названия"
            qty = int(it.get("quantity") or 0)
            cny = Decimal(str(it.get("price") or 0))
            rub = (cny * self.yuan_to_rub).quantize(Decimal("0.01"))
            rows.append({"title": title, "qty": qty, "unit": "штука, шт.", "unit_price_rub": rub})
        return rows

    # ---------- публичный метод ----------

    async def generate_text_form(self, *, cargo_service, cargo_id: int) -> str:
        """
        Заполняет «текстовый» шаблон (без фото) из БД и возвращает путь к временному файлу.

        :param cargo_service: твой CargoService (async)
        :param cargo_id: ID посылки
        :return: str — /tmp/cargo_<ID>_<YYYYMMDD>_form.xlsx
        """
        if not os.path.exists(self.template_path):
            raise FileNotFoundError(f"Excel-шаблон не найден: {self.template_path}")

        rows = await self._load_rows_from_db(cargo_service, cargo_id)
        rows_count = len(rows)

        today = datetime.now().strftime("%Y%m%d")
        tmpdir = tempfile.gettempdir()
        file_path = os.path.join(tmpdir, f"cargo_{cargo_id}_{today}_form.xlsx")

        wb = load_workbook(self.template_path)
        ws = wb[self.sheet_name] if (self.sheet_name and self.sheet_name in wb.sheetnames) else wb.active

        start_row = self.start_row
        end_row = self.end_row
        template_row = start_row
        max_existing = end_row - start_row + 1

        # --- строка «Всего» ---
        total_row_original = await self._find_total_row(ws)
        if total_row_original is None:
            wb.close()
            raise RuntimeError(f"Не найдена строка с текстом '{self.total_label}'")

        move_threshold = int(getattr(self, "move_total_threshold", 29))
        move_total = rows_count > move_threshold

        if move_total:
            await self._cache_total_row(ws, total_row_original)
            await self._remove_merged_ranges_on_row(ws, total_row_original)
            ws.delete_rows(total_row_original)

        if move_total:
            capacity = max_existing
        else:
            capacity = min(max_existing, (total_row_original - start_row))

        # --- заполняем уже существующие строки в шаблоне ---
        rows_written = 0
        write_count = min(rows_count, capacity)
        for i in range(write_count):
            row_idx = start_row + i
            r = rows[i]
            await self._safe_set_cell(ws, row_idx, 2, i + 1)  # №

            for col in self.column_mapping["title"]:
                await self._safe_set_cell(ws, row_idx, col, r["title"])
            for col in self.column_mapping["unit"]:
                await self._safe_set_cell(ws, row_idx, col, r["unit"])
            for col in self.column_mapping["qty"]:
                await self._safe_set_cell(ws, row_idx, col, r["qty"])
            for col in self.column_mapping["unit_price"]:
                await self._safe_set_cell(ws, row_idx, col, r["unit_price_rub"])

        rows_written = write_count

        # --- если данных больше, чем влезает в шаблон ---
        if move_total and rows_count > capacity:
            for i in range(capacity, rows_count):
                row_idx = start_row + i
                ws.insert_rows(row_idx)
                await self._copy_row_format(ws, template_row, row_idx)
                await self._move_merged_cells(ws, template_row, row_idx)

                r = rows[i]
                await self._safe_set_cell(ws, row_idx, 2, i + 1)
                for col in self.column_mapping["title"]:
                    await self._safe_set_cell(ws, row_idx, col, r["title"])
                for col in self.column_mapping["unit"]:
                    await self._safe_set_cell(ws, row_idx, col, r["unit"])
                for col in self.column_mapping["qty"]:
                    await self._safe_set_cell(ws, row_idx, col, r["qty"])
                for col in self.column_mapping["unit_price"]:
                    await self._safe_set_cell(ws, row_idx, col, r["unit_price_rub"])

            rows_written = rows_count

        # --- вернуть «Всего» ---
        if move_total:
            final_row = start_row + rows_written
            await self._restore_total_row(ws, final_row)

        wb.save(file_path)
        wb.close()
        return file_path


# ============================================================
# 3) УДОБНЫЕ ФАСАДЫ
# ============================================================

async def export_cn_msk_goods(*, bot: Bot, cargo_service, cargo_id: int,
                              template_path: Optional[str] = None,
                              max_concurrency: int = 8,
                              photo_inner_padding_px: int = 6) -> str:
    """
    Фасад для CN→MSK (с фото). Возвращает путь к временному .xlsx.
    """
    svc = ExcelExportService(
        bot=bot,
        template_path=template_path,
        max_concurrency=max_concurrency,
        photo_inner_padding_px=photo_inner_padding_px,
    )
    return await svc.generate_goods_sheet(cargo_service=cargo_service, cargo_id=cargo_id)


async def export_text_form(*, cargo_service, cargo_id: int,
                           template_path: Optional[str] = None,
                           sheet_name: Optional[str] = None,
                           start_row: int = 5,
                           end_row: int = 33,
                           total_label: str = "Всего",
                           yuan_to_rub: Optional[Decimal] = None) -> str:
    """
    Фасад для текстового бланка (без фото). Возвращает путь к временному .xlsx.
    """
    svc = ExcelTextFormExportService(
        template_path=template_path,
        sheet_name=sheet_name,
        start_row=start_row,
        end_row=end_row,
        total_label=total_label,
        yuan_to_rub=yuan_to_rub,
    )
    return await svc.generate_text_form(cargo_service=cargo_service, cargo_id=cargo_id)
