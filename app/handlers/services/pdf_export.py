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

    def _register_fonts_and_styles(self):
        """Регистрирует шрифты и создаёт ParagraphStyle через цикл."""
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
                textColor=colors.HexColor("#666666"),
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
        Регистрируем fallback CJK-шрифт (если есть) и создаём стили iOSCJK / iOSCJKSmall.
        Если шрифта нет — стили всё равно создаём, но с базовым шрифтом и wordWrap='CJK'.
        """
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont

        candidates = [
            ("NotoSansSC-Regular", os.path.join("media", "fonts", "NotoSansSC-Regular.otf")),
            ("NotoSansCJKsc-Regular", os.path.join("media", "fonts", "NotoSansCJKsc-Regular.otf")),
            ("DejaVuSans", os.path.join("media", "fonts", "DejaVuSans.ttf")),
        ]
        fallback = None
        for name, path in candidates:
            if os.path.exists(path):
                try:
                    pdfmetrics.registerFont(TTFont(name, path))
                    fallback = name
                    break
                except Exception:
                    pass

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

        add_style("iOSCJK",       fallback or base_font, 11, 14)
        add_style("iOSCJKSmall",  fallback or base_font,  9, 12, colors.HexColor("#333333"))


    def _icon(self, name: str, size: int = 16):
        """Вставка PNG-эмодзи из media/IOSEmoji."""
        path = os.path.join(self.icons_path, name)
        if os.path.exists(path):
            return Image(path, width=size, height=size)
        return ""

    # ========= НОВОЕ: утилита миниатюры из bytes =========
    def _thumb_from_bytes(self, img_bytes: bytes, *, size: int = 48) -> Flowable | str:
        try:
            img = Image(BytesIO(img_bytes))
            img._restrictSize(size, size)
            return img
        except Exception:
            return ""

    # ========= НОВОЕ: общий отчёт с двумя плечами =========

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
                fallback = None  # пойдём на базовый

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
        add_style("iOSCJKSmall", fallback or base_font,  9, 12, colors.HexColor("#333333"))


    # ========= НОВОЕ: пользовательский отчёт «мои товары» =========

    def generate_user_cart_pdf(
        self,
        *,
        file_path: str,
        cargo: dict,
        user: dict,
        items: list[dict],
        settlement_row: dict,
        photos: dict[int, bytes] | None = None,
    ) -> str:
        """
        Пользовательский PDF: «Мои товары в посылке».

        Итоги считаются с взаимозачётом:
            net_due    = max(total_due_usd - total_overpay_usd, 0)
            net_refund = max(total_overpay_usd - total_due_usd, 0)
        """
        doc = SimpleDocTemplate(
            file_path,
            pagesize=A4,
            leftMargin=40, rightMargin=40,
            topMargin=40, bottomMargin=40,
        )
        elements: list = []

        # ---- Заголовок ----
        user_name = html.escape(f"{user.get('name')} {user.get('surname')}" or user.get("name") or "User")
        elements.append(Paragraph(f"Посылка #{cargo.get('id', '-') } — {user_name}", self.styles["iOSTitle"]))

        # ---- Итоги (паспорт + суммы) ----
        s = settlement_row

        goods_usd  = float(s.get("goods_usd", 0))
        goods_paid_usd = float(s.get("goods_paid_usd", 0))
        msk_usd = float(s.get("msk_usd", 0))
        msk_paid_usd = float(s.get("msk_paid_usd", 0))
        by_usd = float(s.get("by_usd", 0))
        by_paid_usd = float(s.get("by_paid_usd", 0))
        advance_usd = float(s.get("advance_usd", 0))

        total_due_raw = float(s.get("total_due_usd", 0))  # долг после авансов/прочего
        total_over_raw = float(s.get("total_overpay_usd", s.get("to_refund_usd", 0)))  # совместимость

        net_due = round(max(total_due_raw  - total_over_raw, 0.0), 2)
        net_refund = round(max(total_over_raw - total_due_raw,  0.0), 2)

        def kv(icon: str, label: str, value_html: str):
            return [
                self._icon(icon),
                Paragraph(f'<b>{html.escape(label)}:</b> {value_html}', self.styles["iOS"]),
            ]

        totals_rows = [
            kv("Label.png", "Название", html.escape(cargo.get("title") or "—")),
            kv("Bookmark.png", "Статус", html.escape(cargo.get("status") or "—")),
            kv("Balance Scale.png", "Всего товаров", html.escape(str(cargo.get("items_count", 0)))),

            kv("Shopping Bags.png", "Товар", f"{goods_usd:.2f}$ (оплачено {goods_paid_usd:.2f} $)"),
            kv("Delivery Truck.png", "CN→MSK", f"{msk_usd:.2f}$ (оплачено {msk_paid_usd:.2f} $)"),
            kv("Delivery Truck.png", "MSK→BY", f"{by_usd:.2f}$ (оплачено {by_paid_usd:.2f} $)"),

            kv("Credit Card.png", "Аванс", f"{advance_usd:.2f}$"),
        ]
        if net_due > 0:
            totals_rows.append(kv("Money Bag.png", "Итого к оплате", f"{net_due:.2f} $"))
        if net_refund > 0:
            totals_rows.append(kv("Return.png", "Итого к возврату", f"{net_refund:.2f} $"))

        totals = Table(totals_rows, colWidths=[20, 440])
        totals.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 0), (0, -1), "CENTER"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ]))
        elements += [totals, Spacer(1, 16)]

        # ---- Таблица товаров ----
        header = ["#", "Фото", "Название", "Кол-во", "Цена $", "Вес (кг)", "Ссылка"]
        data: list[list] = [header]
        photo_map = photos or {}

        for idx, item in enumerate(items, start=1):
            thumb = ""
            item_id = item.get("id")
            if item_id in photo_map and photo_map[item_id]:
                thumb = self._thumb_from_bytes(photo_map[item_id], size=54)

            title_par = Paragraph(html.escape(str(item.get("title", "—"))), self.styles["iOS"])

            url_raw = item.get("source_url") or "-"
            if url_raw and url_raw not in ("-", ""):
                esc = html.escape(url_raw)
                url_par = Paragraph(f'<link href="{esc}">{esc}</link>', self.styles["iOS"])
            else:
                url_par = Paragraph("-", self.styles["iOS"])

            # price = str(item.get("price", 0))
            rate = user.get("rate")
            # print(user)
            if rate:
                try:
                    price_usd = f'{(float(item.get("price", 0)) * float(rate) * int(item.get("quantity"))):.2f}'
                    # print(price_usd)

                except Exception:
                    price_usd = "-"
            else:
                price_usd = "-"

            row = [
                str(idx),
                thumb,
                title_par,
                str(item.get("quantity", 0)),
                price_usd,
                str(item.get("weight_kg", 0)),
                url_par,
            ]
            data.append(row)

        table = Table(data, colWidths=[26, 56, 190, 52, 58, 60, 118])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#007AFF")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("FONTNAME", (0, 0), (-1, -1), self.styles["iOS"].fontName),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.lightgrey]),
        ]))
        elements.append(table)

        doc.build(elements)
        return file_path


    # ========= НОВОЕ: админский отчёт =========

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
                    self.styles["iOS"]
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
            total_due_raw  = float(r.get("total_due_usd", 0))                 # долг после авансов/прочего
            total_over_raw = float(r.get("total_overpay_usd", r.get("to_refund_usd", 0)))  # чистая переплата

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
                self.styles["iOS"]
            )
            msk_cell = Paragraph(
                f'<font name="{self.styles["iOS"].fontName}">{msk_due:.2f}</font>'
                f'<br/><font size=8 color="#666" name="{self.styles["iOSSemiBold"].fontName}">опл. {msk_paid:.2f}</font>',
                self.styles["iOS"]
            )
            by_cell = Paragraph(
                f'<font name="{self.styles["iOS"].fontName}">{by_due:.2f}</font>'
                f'<br/><font size=8 color="#666" name="{self.styles["iOSSemiBold"].fontName}">опл. {by_paid:.2f}</font>',
                self.styles["iOS"]
            )

            table_data.append([
                uid, f"{w:.3f}",
                goods_cell, msk_cell, by_cell,
                f"{adv:.2f}",
                f"{net_refund:.2f}" if net_refund > 0 else "—",
                f"{net_due:.2f}"    if net_due    > 0 else "—",
            ])

        # ---- ИТОГО (по чистым значениям) ----
        total_goods_cell = Paragraph(
            f'<b>{sum_goods_due:.2f}</b>'
            f'<br/><font size=8 color="#666">опл. {sum_goods_paid:.2f}</font>',
            self.styles["iOS"]
        )
        total_msk_cell = Paragraph(
            f'<b>{sum_msk_due:.2f}</b>'
            f'<br/><font size=8 color="#666">опл. {sum_msk_paid:.2f}</font>',
            self.styles["iOS"]
        )
        total_by_cell = Paragraph(
            f'<b>{sum_by_due:.2f}</b>'
            f'<br/><font size=8 color="#666">опл. {sum_by_paid:.2f}</font>',
            self.styles["iOS"]
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


    def generate_cargo_items_pdf(
        self,
        *,
        file_path: str,
        cargo: dict,
        items: list[dict],
        photos: Optional[dict[int, bytes]] = None,
    ) -> str:
        """
        Экспорт всех товаров посылки (landscape A4) с фото, цветом и размером.

        ВАЖНО:
        - Все суммы/курсы считаются в CargoService.get_cargo_info.
        - Здесь только отображение:
            • price_usd берём из item["price_usd"] (Decimal/float/str)
            • в первой колонке: «№ [<b>ID</b>]».
        """

        os.makedirs(os.path.dirname(file_path) or ".", exist_ok=True)

        doc = SimpleDocTemplate(
            file_path,
            pagesize=landscape(A4),
            leftMargin=1.2 * cm, rightMargin=1.2 * cm,
            topMargin=1.2 * cm, bottomMargin=1.2 * cm,
            allowSplitting=1,
        )
        elements: list = []

        items_count = cargo.get("items_count") or len(items)

        elements.append(Paragraph(
            f"Товары посылки #{cargo.get('id', '-')} — {items_count} позиций",
            self.styles["iOSTitle"]
        ))
        elements.append(Spacer(1, 0.3 * cm))

        head = ["#", "Фото", "Название", "Цвет", "Размер", "Кол-во", "Вес (кг)", "Цена $", "Владелец", "Ссылка"]
        data: list[list] = [head]

        photos = photos or {}

        for idx, it in enumerate(items, start=1):
            item_id = it.get("id", "-")

            # ---- № + [ID] жирный
            idx_cell = Paragraph(
                f"{idx} [<b>{html.escape(str(item_id))}</b>]",
                self.styles["iOS"]
            )

            # ---- миниатюра
            thumb: Flowable | str = ""
            if it.get("_photo_bytes"):
                thumb = self._thumb_from_bytes(it["_photo_bytes"], size=56)
            elif photos and item_id in photos:
                thumb = self._thumb_from_bytes(photos[item_id], size=56)

            # ---- поля товара
            title = Paragraph(html.escape(it.get("title", "—")), self.styles["iOS"])
            color = Paragraph(html.escape(str(it.get("color") or "—")), self.styles["iOSCJK"])
            size  = Paragraph(html.escape(str(it.get("size") or "—")), self.styles["iOSCJK"])

            qty    = str(it.get("quantity", 0))
            weight = str(it.get("weight_kg", 0))

            # ---- цена в $, уже посчитанная в CargoService
            raw_price_usd = it.get("price_usd")
            if raw_price_usd is None:
                price_usd = "-"
            else:
                try:
                    price_usd = f"{float(raw_price_usd):.2f}"
                except Exception:
                    price_usd = str(raw_price_usd)

            # ---- владелец
            fio = " ".join(filter(None, [it.get("name"), it.get("surname")])) or "—"
            phone = it.get("phone_number") or "—"
            owner = Paragraph(
                f"<b>ID:</b> {it.get('user_id', '—')}<br/>{html.escape(fio)}<br/>{html.escape(phone)}",
                self.styles["iOS"]
            )

            # ---- ссылка
            url_raw = it.get("source_url") or "-"
            if url_raw and url_raw not in ("", "-"):
                esc = html.escape(url_raw)
                link = Paragraph(f'<link href="{esc}">{esc}</link>', self.styles["iOS"])
            else:
                link = Paragraph("-", self.styles["iOS"])

            data.append([idx_cell, thumb, title, color, size, qty, weight, price_usd, owner, link])

        # ширины колонок
        colWidths = [
            1.4 * cm,  # № + [ID]
            2.0 * cm,  # Фото
            6.0 * cm,  # Название
            2.3 * cm,  # Цвет
            2.3 * cm,  # Размер
            1.3 * cm,  # Кол-во
            1.8 * cm,  # Вес
            1.8 * cm,  # Цена $
            4.6 * cm,  # Владелец
            4.6 * cm,  # Ссылка
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
            ("ALIGN", (5, 1), (7, -1), "RIGHT"),   # qty / вес / цена

            ("LEFTPADDING", (0, 0), (-1, -1), 3),
            ("RIGHTPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 1), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 1), (-1, -1), 3),
        ]))
        elements.append(table)

        doc.build(elements)
        return file_path