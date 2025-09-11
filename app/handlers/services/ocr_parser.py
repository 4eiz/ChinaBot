# app/handlers/services/ocr_parser.py
from typing import Dict, Any, List, Optional
import re


class OCRParser:
    """
    Приводит ответ API к виду:
    {
      "price":    {"best": float|None, "candidates": [str, ...]},
      "quantity": {"best": int|None,   "candidates": [str, ...]},
      "color":    {"best": str|None,   "candidates": [str, ...]},
      "size":     {"best": str|None,   "candidates": [str, ...]},
      "title":    {"best": str|None,   "candidates": [str, ...]},
    }
    """
    _NUM_RE = re.compile(r"\d+(?:[.,]\d+)?")
    _CLEAN_NONNUM = re.compile(r"[^\d.,\-]+")

    @classmethod
    def parse(cls, api_result: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        results = api_result.get("results") or {}
        out: Dict[str, Dict[str, Any]] = {}

        def collect(field: str) -> List[str]:
            items = results.get(field) or []
            seen, vals = set(), []
            for it in items:
                txt = (it.get("text") or "").strip()
                if not txt:
                    continue
                if txt not in seen:
                    vals.append(txt)
                    seen.add(txt)
            return vals

        # ----- price -----
        price_texts = collect("price")
        price_numbers: List[float] = []
        for txt in price_texts:
            nums = cls._NUM_RE.findall(cls._CLEAN_NONNUM.sub("", txt))
            for n in nums:
                try:
                    price_numbers.append(float(n.replace(",", ".")))
                except ValueError:
                    pass
        best_price = min(price_numbers) if price_numbers else None  # обычно финальная — минимальная
        out["price"] = {"best": best_price, "candidates": [str(x) for x in price_numbers] or price_texts}

        # ----- quantity -----
        qty_texts = collect("quantity")
        qty_best: Optional[int] = None
        for txt in qty_texts:
            nums = cls._NUM_RE.findall(cls._CLEAN_NONNUM.sub("", txt))
            if not nums:
                continue
            try:
                q = int(float(nums[0].replace(",", ".")))
                if q >= 1:
                    qty_best = q
                    break
            except ValueError:
                continue
        out["quantity"] = {"best": qty_best, "candidates": qty_texts}

        # ----- color / size -----
        color_texts = collect("color")
        size_texts = collect("size")
        out["color"] = {"best": color_texts[0] if color_texts else None, "candidates": color_texts}
        out["size"] = {"best": size_texts[0] if size_texts else None, "candidates": size_texts}

        # ----- title -----
        # ВАЖНО: больше НЕ подставляем color как title.
        # Берём только если API явно вернёт поле 'title'; иначе пусто.
        title_texts = collect("title")
        out["title"] = {"best": title_texts[0] if title_texts else None, "candidates": title_texts}

        return out
