import base64
import json
import re
from typing import Any, Dict

import aiohttp

import config


PRODUCT_CARD_FIELDS = (
    "title",
    "price",
    "quantity",
    "weight_kg",
    "cn_domestic_shipping",
    "color",
    "size",
    "source_url",
)


def _field_rows(*values: Any) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for value in values:
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    text = str(item.get("text") or item.get("value") or "").strip()
                else:
                    text = str(item or "").strip()
                if text and text not in seen:
                    rows.append({"text": text})
                    seen.add(text)
            continue

        text = str(value or "").strip()
        if text and text not in seen:
            rows.append({"text": text})
            seen.add(text)
    return rows


def _normalize_product_title(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    lowered = text.lower()
    generic_map = [
        ("футбол", "Футболка"),
        ("кроссов", "Кроссовки"),
        ("кед", "Кеды"),
        ("джинс", "Джинсы"),
        ("свитер", "Свитер"),
        ("кофт", "Кофта"),
        ("толстов", "Толстовка"),
        ("худи", "Худи"),
        ("брюки", "Брюки"),
        ("штаны", "Штаны"),
        ("очки", "Очки"),
    ]
    for needle, title in generic_map:
        if needle in lowered:
            return title
    stop_words = {"мужская", "мужской", "женская", "женский", "детская", "детский"}
    parts = [part for part in re.split(r"\s+", text) if part.lower() not in stop_words]
    return " ".join(parts[:3]).strip() or text


def _normalize_title_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in rows:
        text = _normalize_product_title(row.get("text"))
        if text and text not in seen:
            normalized.append({"text": text})
            seen.add(text)
    return normalized


def normalize_result(raw: Dict[str, Any]) -> Dict[str, Any]:
    results = raw.get("results") if isinstance(raw, dict) else None
    if isinstance(results, dict):
        normalized = {
            "results": {
                field: _field_rows(results.get(field))
                for field in PRODUCT_CARD_FIELDS
            }
        }
        normalized["results"]["title"] = _normalize_title_rows(normalized["results"]["title"])
        return normalized

    normalized = {
        "results": {
            field: _field_rows(
                raw.get(field),
                (raw.get(field) or {}).get("candidates") if isinstance(raw.get(field), dict) else None,
            )
            for field in PRODUCT_CARD_FIELDS
        }
    }
    normalized["results"]["title"] = _normalize_title_rows(normalized["results"]["title"])
    return normalized


def extract_json_object(text: str) -> Dict[str, Any]:
    content = str(text or "").strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*", "", content, flags=re.IGNORECASE)
        content = re.sub(r"\s*```$", "", content).strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    start = content.find("{")
    end = content.rfind("}")
    if start >= 0 and end > start:
        return json.loads(content[start:end + 1])
    raise RuntimeError(f"AI response is not JSON: {content[:180] or 'empty response'}")


class RecognitionClient:
    """
    Product-card recognition through sub2api-compatible /chat/completions.
    Model and key are configured in the ChinaBot .env file.
    """

    def __init__(self):
        self.base_url = self._normalize_base_url(config.PRODUCT_RECOGNITION_BASE_URL or "")
        self.api_key = config.PRODUCT_RECOGNITION_API_KEY
        self.model = config.PRODUCT_RECOGNITION_MODEL or "antigravity"
        self.api_mode = self._normalize_api_mode(config.PRODUCT_RECOGNITION_API_MODE)
        self.timeout = config.PRODUCT_RECOGNITION_TIMEOUT_SECONDS

    def _normalize_base_url(self, raw: str) -> str:
        value = raw.strip().rstrip("/")
        if not value:
            return ""
        if value.endswith(("/v1", "/messages", "/chat/completions")):
            return value
        return f"{value}/v1"

    def _normalize_api_mode(self, raw: str | None = None) -> str:
        mode = str(raw or "antigravity").strip().lower()
        if mode in {"messages", "anthropic"}:
            return "antigravity"
        if mode in {"chat-completions", "openai"}:
            return "chat_completions"
        return mode if mode in {"antigravity", "chat_completions"} else "antigravity"

    def _models(self) -> list[str]:
        models: list[str] = []
        configured = self.model or "antigravity"
        for model in str(configured).split(","):
            model = model.strip()
            if model and model not in models:
                models.append(model)
        return models or ["antigravity"]

    def _prompt(self) -> str:
        return (
            "Extract product data from a screenshot of a Chinese marketplace product card. "
            "Return only a valid JSON object, with no Markdown and no explanation. "
            "The JSON schema must be exactly: "
            '{"results":{"title":[{"text":"..."}],"price":[{"text":"..."}],"quantity":[{"text":"..."}],'
            '"weight_kg":[],"cn_domestic_shipping":[],"color":[{"text":"..."}],"size":[{"text":"..."}],"source_url":[]}}. '
            'Every value inside results must be an array of objects like {"text":"value"}. Use an empty array when unknown. '
            'title: short generic Russian product type only, without brand, model, gender, color, or size. '
            'Examples: use "Футболка" instead of "Мужская футболка Joma"; use "Кроссовки" instead of brand-heavy names. '
            "price: current selected SKU price in CNY, number only, no currency. Prefer coupon/final price when visible; ignore crossed old prices. "
            'quantity: visible quantity counter value; use "1" if no counter is visible. '
            "color and size: read selected product variants from top to bottom. The first selected variant group is color, the next selected variant group is size. "
            "Detect selected variants by red border, active card, highlighted text, selected SKU, or the Chinese selected marker. "
            "If only one selected variant group is visible, put it in color and leave size empty. "
            "weight_kg: visible product weight in kilograms, number only; do not invent it. "
            'cn_domestic_shipping: visible China domestic shipping cost in CNY, number only. If free shipping is explicitly visible, return "0". '
            "source_url: product URL only if it is clearly visible. "
            "Required fields for adding a product are title, price, quantity, color, and source_url. Size is optional. "
            "Do not invent weight, shipping, source URL, or missing variants."
        )

    def _endpoint(self, api_mode: str | None = None) -> str:
        mode = self._normalize_api_mode(api_mode or self.api_mode)
        if mode == "antigravity":
            if self.base_url.endswith("/messages"):
                return self.base_url
            return f"{self.base_url}/messages"
        if self.base_url.endswith("/chat/completions"):
            return self.base_url
        return f"{self.base_url}/chat/completions"

    def _headers(self, api_mode: str | None = None) -> dict[str, str]:
        mode = self._normalize_api_mode(api_mode or self.api_mode)
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        if mode == "antigravity":
            headers["anthropic-version"] = "2023-06-01"
        return headers

    def _payload(self, image_base64: str, model: str, content_type: str, api_mode: str | None = None) -> dict[str, Any]:
        mode = self._normalize_api_mode(api_mode or self.api_mode)
        if mode == "antigravity":
            return {
                "model": model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": self._prompt()},
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": content_type,
                                    "data": image_base64,
                                },
                            },
                        ],
                    }
                ],
                "temperature": 0.1,
                "stream": False,
                "max_tokens": 900,
            }

        return {
            "model": model,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": self._prompt()},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{content_type};base64,{image_base64}",
                                "detail": "high",
                            },
                        },
                    ],
                }
            ],
            "max_tokens": 900,
        }

    def _message_text(self, data: dict[str, Any], api_mode: str | None = None) -> str:
        mode = self._normalize_api_mode(api_mode or self.api_mode)
        if mode == "antigravity":
            content = data.get("content")
            if isinstance(content, list):
                chunks: list[str] = []
                for part in content:
                    if isinstance(part, dict) and part.get("text") is not None:
                        chunks.append(str(part.get("text")))
                    elif part is not None and not isinstance(part, dict):
                        chunks.append(str(part))
                return "\n".join(chunks)
            return "" if content is None else str(content)
        return str(data.get("choices", [{}])[0].get("message", {}).get("content", "") or "")

    async def recognize(self, image_bytes: bytes, content_type: str = "image/jpeg") -> Dict[str, Any]:
        if not self.base_url:
            raise RuntimeError("PRODUCT_RECOGNITION_BASE_URL is not configured")

        image_base64 = base64.b64encode(image_bytes).decode("ascii")
        retry_statuses = {400, 404, 422}
        last_error = ""

        async with aiohttp.ClientSession() as session:
            for model in self._models():
                payload = self._payload(image_base64, model=model, content_type=content_type, api_mode=self.api_mode)
                async with session.post(
                    self._endpoint(self.api_mode),
                    headers=self._headers(self.api_mode),
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                ) as resp:
                    text = await resp.text()
                    if resp.status not in (200, 201):
                        last_error = f"Sub2API error {resp.status}: {text[:300]}"
                        if resp.status in retry_statuses:
                            continue
                        raise RuntimeError(last_error)
                    try:
                        data = json.loads(text)
                    except json.JSONDecodeError as exc:
                        content_type_header = resp.headers.get("content-type", "")
                        raise RuntimeError(
                            f"Sub2API returned non-JSON response ({content_type_header}): {text[:300]}"
                        ) from exc

                message = self._message_text(data, self.api_mode)
                parsed = extract_json_object(message)
                return normalize_result(parsed)

        raise RuntimeError(last_error or "Sub2API model did not respond")
