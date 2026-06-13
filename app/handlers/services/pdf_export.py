import os
import html
from io import BytesIO
from typing import List, Dict, Optional

from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, Flowable
)
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import cm
from reportlab.pdfbase.cidfonts import UnicodeCIDFont


class PDFExportService:
    """Сервис генерации PDF для посылки и её товаров — iOS-стиль + PNG-эмодзи."""

    def __init__(self):
        self._register_fonts_and_styles()
        self.icons_path = os.path.join("media", "IOSEmoji")

    # ================= ШРИФТЫ и СТИЛИ =================

    def _register_fonts_and_styles(self):
        """Регистрирует шрифты и создаёт ParagraphStyle."""
        fonts = {
            "iOS": ("SFPro", os.path.join("media", "fonts", "SF-Pro-Display-Regular.ttf")),
            "iOSSemiBold": ("SFPro-SemiBold", os.path.join("media", "fonts", "SF-Pro-Display-Semibold.ttf")),
            "iOSBold": ("SFPro-Bold", os.path.join("media", "fonts", "SF-Pro-Display-Bold.ttf")),
        }
        registered = {}
        for style_name, (font_name, path) in fonts.items():
            if os.path.exists(path):
                pdfmetrics.registerFont(TTFont(font_name, path))
                registered[style_name] = font_name
            else:
                registered[style_name] = "Helvetica"

        self.styles = getSampleStyleSheet()
        for style_name, font in registered.items():
            self.styles.add(ParagraphStyle(
                name=style_name,
                fontName=font,
                fontSize=11,
                leading=14,
                spaceAfter=6,
            ))

        # доп. стили для шапок/мелких ссылок
        if "iOSCaption" not in self.styles:
            self.styles.add(ParagraphStyle(
                name="iOSCaption",
                fontName=registered["iOS"],
                fontSize=9,
                leading=12,
                textColor=colors.HexColor("#000000"),
                spaceAfter=4,
            ))
        if "iOSTitle" not in self.styles:
            self.styles.add(ParagraphStyle(
                name="iOSTitle",
                fontName=registered["iOSBold"],
                fontSize=16,
                leading=20,
                spaceAfter=12,
            ))

        self._ensure_cjk_styles()

    def _ensure_cjk_styles(self):
        """
        Подключаем CJK-шрифт. Порядок:
        1) Файлы из media/fonts: NotoSansSC / NotoSansCJKsc / DejaVuSans (TTF/OTF)
        2) Встроенный CID-шрифт ReportLab: STSong-Light (китайский)
        3) В крайнем случае — базовый шрифт, но с wordWrap='CJK'
        """
        fallback = None

        # 1) Пытаемся найти локальные файлы
        candidates = [
            ("NotoSansSC-Regular", os.path.join("media", "fonts", "NotoSansSC-Regular.otf")),
            ("NotoSansCJKsc-Regular", os.path.join("media", "fonts", "NotoSansCJKsc-Regular.otf")),
            ("DejaVuSans", os.path.join("media", "fonts", "DejaVuSans.ttf")),
        ]
        for name, path in candidates:
            if os.path.exists(path):
                try:
                    pdfmetrics.registerFont(TTFont(name, path))
                    fallback = name
                    break
                except Exception:
                    pass

        # 2) Если файлов нет — берём встроенный CID-шрифт (китайский упрощённый)
        if not fallback:
            try:
                pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
                fallback = "STSong-Light"
            except Exception:
                fallback = None

        base_font = self.styles["iOS"].fontName

        def add_style(name, font_name, size, leading, color=None):
            if name not in self.styles.byName:
                self.styles.add(ParagraphStyle(
                    name=name,
                    fontName=font_name,
                    fontSize=size,
                    leading=leading,
                    wordWrap="CJK",
                    textColor=(color or colors.black),
                    spaceAfter=6 if size >= 11 else 4,
                ))

        add_style("iOSCJK",      fallback or base_font, 11, 14)
        add_style("iOSCJKSmall", fallback or base_font, 9, 12, colors.HexColor("#333333"))

    # ================= УТИЛИТЫ =================

    def _icon(self, name: str, size: int = 16):
        """Вставка PNG-эмодзи из media/IOSEmoji."""
        path = os.path.join(self.icons_path, name)
        if os.path.exists(path):
            return Image(path, width=size, height=size)
        return ""

    def _thumb_from_bytes(self, img_bytes: bytes, *, size: int = 48) -> Flowable | str:
        """Миниатюра изображения из bytes."""
        try:
            img = Image(BytesIO(img_bytes))
            img._restrictSize(size, size)
            return img
        except Exception:
            return ""

    def _render_title_block(self, item: dict) -> Paragraph:
        """
        Название товара в одном столбце:
        - строка 1: Название (красивый базовый шрифт)
        - строка 2+: [ID], Цвет: <CJK>, Размер: <CJK>
        Шрифт CJK используется ТОЛЬКО для значений цвета/размера.
        """
        base_style = self.styles["iOS"]
        base_font = base_style.fontName
        cjk_font = self.styles["iOSCJK"].fontName

        title = html.escape(str(item.get("title") or "—"))

        # первая строка: название красивым шрифтом
        html_parts = [f"<font name='{base_font}'>{title}</font>"]

        sub_lines = []

        # ID — обычным шрифтом
        if item.get("id"):
            sub_lines.append(f"[ID: {item['id']}]")

        # Цвет: значение цвет CJK-шрифтом
        if item.get("color"):
            color_val = html.escape(str(item["color"]))
            sub_lines.append(
                f"Цвет: <font name='{cjk_font}'>{color_val}</font>"
            )

        # Размер: значение размер CJK-шрифтом
        if item.get("size"):
            size_val = html.escape(str(item["size"]))
            sub_lines.append(
                f"Размер: <font name='{cjk_font}'>{size_val}</font>"
            )

        if sub_lines:
            html_parts.append(
                "<br/><font size='8' color='#171717'>" +
                "<br/>".join(sub_lines) +
                "</font>"
            )

        html_full = "".join(html_parts)
        # ВАЖНО: стиль — обычный iOS, чтобы не растягивало кириллицу/латиницу
        return Paragraph(html_full, base_style)

    def _render_price_block(self, item: dict) -> Paragraph:
        """
        Цена в одном столбце, три строки:
        - товар/шт
        - дост./шт
        - итого за N шт
        Используем нормальный iOS-шрифт, CJK тут не нужен.
        """
        from decimal import Decimal

        try:
            qty = Decimal(str(item.get("quantity") or 1))

            # поддерживаем оба варианта ключей: goods_usd_per_unit и price_usd_per_unit
            g_val = item.get("goods_usd_per_unit", item.get("price_usd_per_unit"))
            d_val = item.get("delivery_per_unit_usd")
            total_val = item.get("final_total_usd")

            g = Decimal(str(g_val))
            d = Decimal(str(d_val))
            total = Decimal(str(total_val))


            # оригинальная цена в юанях за 1 шт (если есть в payload)
            # поддерживаем разные ключи из БД/экспорта
            cny_raw = (
                item.get("unit_price_cny")
                or item.get("price_cny_per_unit")
                or item.get("price_cny")
                or item.get("price_cny_unit")
                or item.get("price")  # часто цена в БД хранится в юанях
            )
            cny_unit = None
            try:
                if cny_raw not in (None, "", "-"):
                    cny_unit = Decimal(str(cny_raw))
            except Exception:
                cny_unit = None
        except Exception:
            return Paragraph("-", self.styles["iOS"])

        html_price = (
            (f"цена(¥)/шт: {cny_unit:.2f}¥<br/>" if cny_unit is not None else "")
            + f"товар/шт: {g:.2f}$<br/>"
            + f"дост./шт: {d:.2f}$<br/>"
            + f"<b>итого за {qty} шт: {total:.2f}$</b>"
        )
        # ТУТ специально используем iOS, чтобы текст был «красивый» и не расползался
        return Paragraph(html_price, self.styles["iOS"])


    # ================== ЮЗЕРСКИЙ ОТЧЁТ «МОИ ТОВАРЫ» ==================

    def generate_user_cart_pdf(
        self,
        *,
        file_path: str,
        cargo: dict,
        user: dict,
        items: list[dict],
        settlement_row: dict,
        photos: Optional[dict[int, bytes]] = None,
    ) -> str:
        """
        Юзерский отчёт по товарам в посылке.

        items ДОЛЖНЫ уже содержать:
          - price_usd_per_unit / goods_usd_per_unit
          - delivery_per_unit_usd
          - final_total_usd

        Все расчёты выполняются в CargoService, здесь только отображение.
        """
        from decimal import Decimal

        os.makedirs(os.path.dirname(file_path) or ".", exist_ok=True)

        doc = SimpleDocTemplate(
            file_path,
            pagesize=A4,
            leftMargin=18,
            rightMargin=18,
            topMargin=18,
            bottomMargin=18,
        )
        elements: list = []

        # ---- Заголовок ----
        title = cargo.get("title") or f"Посылка #{cargo.get('id', '-')}"
        elements.append(Paragraph(f"Ваши товары в посылке: {title}", self.styles["iOSTitle"]))
        elements.append(Spacer(1, 10))

        # ---- Краткая сводка по оплате ----
        total_goods_usd = settlement_row.get("goods_usd") or 0
        total_delivery_usd = (settlement_row.get("msk_usd") or 0) + (settlement_row.get("by_usd") or 0)
        referral_discount_usd = settlement_row.get("referral_discount_usd") or 0
        total_due_usd = settlement_row.get("total_due_usd") or 0
        referral_line = (
            f"Реферальная скидка: <b>-{referral_discount_usd:.2f}$</b><br/>"
            if referral_discount_usd > 0 else ""
        )

        summary_text = (
            f"💰 <b>Сводка по оплате</b><br/>"
            f"Товары: <b>{total_goods_usd:.2f}$</b><br/>"
            f"Доставка: <b>{total_delivery_usd:.2f}$</b><br/>"
            f"{referral_line}"
            f"Итого к оплате: <b>{total_due_usd:.2f}$</b>"
        )
        elements.append(Paragraph(summary_text, self.styles["iOSCJK"]))
        elements.append(Spacer(1, 14))

        # ---- Таблица товаров ----
        header = ["#", "Фото", "Товар", "Кол-во", "Цена (USD)", "Вес (кг)", "Ссылка"]
        data: list[list] = [header]
        photo_map = photos or {}

        for idx, item in enumerate(items, start=1):
            thumb = ""
            item_id = item.get("id")
            if item_id in photo_map and photo_map[item_id]:
                thumb = self._thumb_from_bytes(photo_map[item_id], size=54)

            # --- Название + [ID] + цвет/размер (одна колонка) ---
            title_par = self._render_title_block(item)

            # --- URL ---
            url_raw = item.get("source_url") or "-"
            if url_raw and url_raw not in ("-", ""):
                esc = html.escape(url_raw)
                url_par = Paragraph(f'<link href="{esc}">{esc}</link>', self.styles["iOSCJKSmall"])
            else:
                url_par = Paragraph("-", self.styles["iOSCJKSmall"])

            # --- Количество ---
            qty = Decimal(str(item.get("quantity") or 1))

            # --- Цена: 3 строки (товар/шт, доставка/шт, итог за все) ---
            price_cell = self._render_price_block(item)

            # --- Вес ---
            weight_val = item.get("weight_kg", 0)
            try:
                weight_str = f"{float(weight_val):.3f}"
            except Exception:
                weight_str = str(weight_val)

            row = [
                str(idx),
                thumb,
                title_par,
                str(qty),
                price_cell,
                weight_str,
                url_par,
            ]
            data.append(row)

        table = Table(data, colWidths=[20, 50, 220, 40, 95, 55, 120])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#007AFF")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("FONTNAME", (0, 0), (-1, 0), self.styles["iOSSemiBold"].fontName),
            ("FONTSIZE", (0, 0), (-1, 0), 9),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.lightgrey]),
            ("ALIGN", (0, 1), (0, -1), "RIGHT"),   # #
            ("ALIGN", (3, 1), (5, -1), "RIGHT"),   # qty / price / weight
            ("LEFTPADDING", (0, 0), (-1, -1), 3),
            ("RIGHTPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 1), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 1), (-1, -1), 3),
        ]))
        elements.append(table)

        doc.build(elements)
        return file_path

    # ================== АДМИНСКИЙ ОТЧЁТ ПО ПОСЫЛКЕ ==================

    def generate_admin_cargo_pdf(
        self,
        *,
        file_path: str,
        cargo: dict,
        per_user_rows: list[dict],
        legs: dict
    ) -> str:
        """Админ-отчёт: расширенная шапка посылки + таблица по людям в landscape A4
        С учётом взаимозачёта: переплаты сначала покрывают долги, остаток — к возврату.
        """

        doc = SimpleDocTemplate(
            file_path,
            pagesize=landscape(A4),
            leftMargin=1.2 * cm, rightMargin=1.2 * cm,
            topMargin=1.2 * cm, bottomMargin=1.2 * cm,
        )
        elements = []

        # ---- заголовок ----
        elements.append(Paragraph(
            f"Админ-отчёт — Посылка #{cargo['id']}",
            self.styles["iOSTitle"]
        ))
        elements.append(Spacer(1, 0.3 * cm))

        # ---- паспорт посылки ----
        def info_row(icon: str, label: str, value: str):
            return [
                self._icon(icon),
                Paragraph(
                    f'<font name="{self.styles["iOSSemiBold"].fontName}">{label}:</font> '
                    f'<font name="{self.styles["iOS"].fontName}">{value}</font>',
                    self.styles["iOSCJK"]
                )
            ]

        total_w = legs.get("total_weight_kg", 0)
        charge_w = legs.get("chargeable_weight_kg", 0)
        cnmsk_cost = legs.get("cn_to_msk", {}).get("delivery_cost_usd", 0)
        r1 = legs.get("cn_to_msk", {}).get("rate_per_kg_usd", 0)
        mskby_cost = legs.get("msk_to_by", {}).get("delivery_cost_usd", 0)
        mskby_rule = "мин. 10$, +1$/кг после 10 кг"

        info_rows = [
            info_row("Label.png",          "Название", cargo.get("title") or "—"),
            info_row("File Folder.png",    "Тип", cargo.get("type_name") or "—"),
            info_row("Bookmark.png",       "Редактирование", cargo.get("status") or "—"),
            info_row("Credit Card.png",    "Оплата", cargo.get("payment_status") or "—"),
            info_row("Delivery Truck.png", "Маршрут", cargo.get("route_status") or "—"),
            info_row("Balance Scale.png",  "Вес посылки", f"{total_w} кг (расч.: {charge_w} кг)"),
            info_row("Money Bag.png",      "CN→MSK (всего)", f"{cnmsk_cost}$ (тариф {r1}$/кг)"),
            info_row("Money Bag.png",      "MSK→BY (всего)", f"{mskby_cost}$ ({mskby_rule})"),
            info_row("Bar Chart.png",      "Кол-во товаров", cargo.get("items_count") or 0),
        ]

        info_table = Table(info_rows, colWidths=[0.7 * cm, 25 * cm])
        info_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("LEFTPADDING", (0, 0), (-1, -1), 2),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]))
        elements.append(info_table)
        elements.append(Spacer(1, 0.5 * cm))

        # ---- таблица по людям (чистые значения после взаимозачёта) ----
        head = [
            "User ID", "Вес, кг",
            "Товар / опл., $",
            "CN→MSK / опл., $",
            "MSK→BY / опл., $",
            "Аванс, $", "К возврату, $", "Итого к оплате, $"
        ]
        table_data = [head]

        sum_w = sum_goods_due = sum_goods_paid = 0.0
        sum_msk_due = sum_msk_paid = 0.0
        sum_by_due = sum_by_paid = 0.0
        sum_adv = sum_refund_net = sum_due_net = 0.0

        for r in per_user_rows:
            uid = str(r.get("user_id", ""))
            w = float(r.get("weight_kg", 0))

            goods_due  = float(r.get("goods_usd", 0))
            goods_paid = float(r.get("goods_paid_usd", 0))
            msk_due    = float(r.get("msk_usd", 0))
            msk_paid   = float(r.get("msk_paid_usd", 0))
            by_due     = float(r.get("by_usd", 0))
            by_paid    = float(r.get("by_paid_usd", 0))

            adv = float(r.get("advance_usd", 0))

            # исходные агрегаты
            total_due_raw  = float(r.get("total_due_usd", 0))
            total_over_raw = float(r.get("total_overpay_usd", r.get("to_refund_usd", 0)))

            # взаимозачёт
            net_due = round(max(total_due_raw - total_over_raw, 0.0), 2)
            net_refund = round(max(total_over_raw - total_due_raw, 0.0), 2)

            sum_w += w
            sum_goods_due  += goods_due;  sum_goods_paid += goods_paid
            sum_msk_due    += msk_due;    sum_msk_paid   += msk_paid
            sum_by_due     += by_due;     sum_by_paid    += by_paid
            sum_adv        += adv
            sum_refund_net += net_refund
            sum_due_net    += net_due

            goods_cell = Paragraph(
                f'<font name="{self.styles["iOS"].fontName}">{goods_due:.2f}</font>'
                f'<br/><font size=8 color="#666" name="{self.styles["iOSSemiBold"].fontName}">опл. {goods_paid:.2f}</font>',
                self.styles["iOSCJK"]
            )
            msk_cell = Paragraph(
                f'<font name="{self.styles["iOS"].fontName}">{msk_due:.2f}</font>'
                f'<br/><font size=8 color="#666" name="{self.styles["iOSSemiBold"].fontName}">опл. {msk_paid:.2f}</font>',
                self.styles["iOSCJK"]
            )
            by_cell = Paragraph(
                f'<font name="{self.styles["iOS"].fontName}">{by_due:.2f}</font>'
                f'<br/><font size=8 color="#666" name="{self.styles["iOSSemiBold"].fontName}">опл. {by_paid:.2f}</font>',
                self.styles["iOSCJK"]
            )

            table_data.append([
                uid, f"{w:.3f}",
                goods_cell, msk_cell, by_cell,
                f"{adv:.2f}",
                f"{net_refund:.2f}" if net_refund > 0 else "—",
                f"{net_due:.2f}"    if net_due    > 0 else "—",
            ])

        # ---- ИТОГО ----
        total_goods_cell = Paragraph(
            f'<b>{sum_goods_due:.2f}</b>'
            f'<br/><font size=8 color="#666">опл. {sum_goods_paid:.2f}</font>',
            self.styles["iOSCJK"]
        )
        total_msk_cell = Paragraph(
            f'<b>{sum_msk_due:.2f}</b>'
            f'<br/><font size=8 color="#666">опл. {sum_msk_paid:.2f}</font>',
            self.styles["iOSCJK"]
        )
        total_by_cell = Paragraph(
            f'<b>{sum_by_due:.2f}</b>'
            f'<br/><font size=8 color="#666">опл. {sum_by_paid:.2f}</font>',
            self.styles["iOSCJK"]
        )

        table_data.append([
            Paragraph("<b>ИТОГО</b>", self.styles["iOSBold"]),
            f"{sum_w:.3f}",
            total_goods_cell, total_msk_cell, total_by_cell,
            f"{sum_adv:.2f}",
            f"{sum_refund_net:.2f}" if sum_refund_net > 0 else "—",
            f"{sum_due_net:.2f}"    if sum_due_net    > 0 else "—",
        ])

        colWidths = [3 * cm, 2.2 * cm, 4 * cm, 4 * cm, 4 * cm, 2.6 * cm, 2.8 * cm, 3.2 * cm]
        table = Table(table_data, colWidths=colWidths, repeatRows=1)

        style = TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#007AFF")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("FONTNAME", (0, 0), (-1, 0), self.styles["iOSSemiBold"].fontName),
            ("FONTSIZE", (0, 0), (-1, 0), 9),
            ("ALIGN", (0, 0), (-1, 0), "CENTER"),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 8),

            ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
            ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.whitesmoke, colors.lightgrey]),

            ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#EFEFF4")),
            ("FONTNAME", (0, -1), (-1, -1), self.styles["iOSBold"].fontName),

            ("ALIGN", (0, 1), (0, -1), "LEFT"),    # User ID
            ("ALIGN", (1, 1), (-1, -1), "RIGHT"),  # числа
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("FONTSIZE", (0, 1), (-1, -1), 8),

            ("LEFTPADDING", (0, 0), (-1, -1), 3),
            ("RIGHTPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 1), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 1), (-1, -1), 3),
        ])
        table.setStyle(style)
        elements.append(table)

        doc.build(elements)
        return file_path

    # ================== АДМИНСКИЙ ЭКСПОРТ ВСЕХ ТОВАРОВ ==================

    def generate_cargo_items_pdf(
        self,
        *,
        file_path: str,
        cargo: dict,
        items: list[dict],
        photos: Optional[dict[int, bytes]] = None,
    ) -> str:
        """
        Экспорт всех товаров посылки (landscape A4).

        items ДОЛЖНЫ уже содержать поля:
          - goods_usd_per_unit
          - delivery_per_unit_usd
          - final_total_usd

        Все расчёты выполняются в CargoService.get_admin_items_export_payload.
        Здесь — только отображение.
        """
        from decimal import Decimal

        os.makedirs(os.path.dirname(file_path) or ".", exist_ok=True)

        doc = SimpleDocTemplate(
            file_path,
            pagesize=landscape(A4),
            leftMargin=1.2 * cm,
            rightMargin=1.2 * cm,
            topMargin=1.2 * cm,
            bottomMargin=1.2 * cm,
            allowSplitting=1,
        )
        elements: list = []

        items_count = cargo.get("items_count") or len(items)

        elements.append(Paragraph(
            f"Товары посылки #{cargo.get('id', '-')} — {items_count} позиций",
            self.styles["iOSTitle"]
        ))
        elements.append(Spacer(1, 0.3 * cm))

        # Упрощаем таблицу: название+ID+цвет+размер в одной колонке
        head = ["#", "Фото", "Товар", "Кол-во", "Вес (кг)", "Цена $", "Владелец", "Ссылка"]
        data: list[list] = [head]

        photos = photos or {}

        for idx, it in enumerate(items, start=1):
            item_id = it.get("id", "-")

            # ---- № + [ID] в одной строке ----
            idx_cell = Paragraph(
                f"{idx} [<b>{html.escape(str(item_id))}</b>]",
                self.styles["iOSCJK"]
            )

            # ---- миниатюра ----
            thumb = ""
            if it.get("_photo_bytes"):
                thumb = self._thumb_from_bytes(it["_photo_bytes"], size=56)
            elif photos and item_id in photos:
                thumb = self._thumb_from_bytes(photos[item_id], size=56)

            # ---- Товар (название + ID + цвет + размер) ----
            title_par = self._render_title_block(it)

            # ---- Количество / вес ----
            qty = Decimal(str(it.get("quantity") or 1))
            weight_val = it.get("weight_kg", 0)
            try:
                weight = f"{float(weight_val):.3f}"
            except Exception:
                weight = str(weight_val)

            # ---- Цена: 3 строки ----
            price_cell = self._render_price_block(it)

            # ---- владелец ----
            fio = " ".join(filter(None, [it.get("name"), it.get("surname")])) or "—"
            phone = it.get("phone_number") or "—"
            owner = Paragraph(
                f"<b>ID:</b> {it.get('user_id', '—')}<br/>{html.escape(fio)}<br/>{html.escape(phone)}",
                self.styles["iOSCaption"]
            )

            # ---- ссылка ----
            url_raw = it.get("source_url") or "-"
            if url_raw and url_raw not in ("", "-"):
                esc = html.escape(url_raw)
                link = Paragraph(f'<link href="{esc}">{esc}</link>', self.styles["iOSCaption"])
            else:
                link = Paragraph("-", self.styles["iOSCaption"])

            data.append([idx_cell, thumb, title_par, str(qty), weight, price_cell, owner, link])

        # ширины колонок
        colWidths = [
            1.8 * cm,  # № + [ID]
            2.0 * cm,  # Фото
            7.5 * cm,  # Товар (название+ID+цвет+размер)
            1.5 * cm,  # Кол-во
            2.2 * cm,  # Вес
            4.0 * cm,  # Цена $ (3 строки)
            5.0 * cm,  # Владелец
            5.0 * cm,  # Ссылка
        ]

        table = Table(data, colWidths=colWidths, repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#007AFF")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("FONTNAME", (0, 0), (-1, 0), self.styles["iOSSemiBold"].fontName),
            ("FONTSIZE", (0, 0), (-1, 0), 9),
            ("ALIGN", (0, 0), (-1, 0), "CENTER"),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 8),

            ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.lightgrey]),

            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),

            ("ALIGN", (0, 1), (0, -1), "LEFT"),    # № + [ID]
            ("ALIGN", (3, 1), (5, -1), "RIGHT"),   # qty / вес / цена

            ("LEFTPADDING", (0, 0), (-1, -1), 3),
            ("RIGHTPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 1), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 1), (-1, -1), 3),
        ]))
        elements.append(table)

        doc.build(elements)
        return file_path
