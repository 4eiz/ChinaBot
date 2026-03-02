from aiogram.types import FSInputFile
from pathlib import Path
from typing import Union


class PhotoBank:
    """📦 Банк фотографий, которые используются в боте"""

    BASE = Path()

    # 📷 Анкета
    SLIDE1 = BASE / "media/images/slide1.jpg"
    SLIDE2 = BASE / "media/images/slide2.jpg"
    SLIDE3 = BASE / "media/images/slide3.jpg"
    SLIDE4 = BASE / "media/images/slide4.jpg"

    # 🧭 Основные фото
    MENU_IMAGE = BASE / "media/images/menu.jpg"
    PROFILE_IMAGE = BASE / "media/images/profile.jpg"
    CARGOS_IMAGE = BASE / "media/images/cargos.jpg"
    INFO_IMAGE = BASE / "media/images/info.jpg"
    SUPPORT_IMAGE = BASE / "media/images/support.jpg"

    # 🔐 Админка
    ADMIN_PANEL_IMAGE = BASE / "media/images/admin.jpg"

    # 📦 Категории
    CATEGORY_HOUSEHOLD = BASE / "media/images/categories/household.jpg"
    CATEGORY_CLOTHES = BASE / "media/images/categories/clothes.jpg"
    CATEGORY_SHOES = BASE / "media/images/categories/shoes.jpg"

    # 🧾 Telegram file_ids
    TELEGRAM_FILE_IDS = {
        "success": "AgACAgUAAxkBAAIBY2ZVc...",
        "error": "AgACAgUAAxkBAAIBZmZUd..."
    }

    @classmethod
    def get_file(cls, name: str) -> Union[FSInputFile, str]:
        if name in cls.TELEGRAM_FILE_IDS:
            return cls.TELEGRAM_FILE_IDS[name]

        path = getattr(cls, name, None)
        if path and Path(path).exists():
            return FSInputFile(path)  # ✅ Правильный способ

        raise FileNotFoundError(f"Файл или ключ {name} не найден в PhotoBank")