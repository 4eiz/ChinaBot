from typing import Dict, Any
import config
import aiohttp
import asyncio


class RecognitionClient:
    """
    Сервис распознавания скриншотов заказов через твой DRF API.
    Автоматически получает JWT токен перед каждым запросом.
    """

    def __init__(self):
        self.api_url = config.API_URL
        self.ocr_url = f'{self.api_url}/api/v1/predictions/'
        self.auth_url = f'{self.api_url}/api/v1/token/'
        self.username = config.API_USERNAME
        self.password = config.API_PASSWORD

    async def _get_token(self) -> str:
        """Запрашивает новый access-токен."""
        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.auth_url,
                json={"username": self.username, "password": self.password}
            ) as resp:
                if resp.status not in (200, 201):
                    text = await resp.text()
                    raise RuntimeError(f"Auth error {resp.status}: {text}")
                data = await resp.json()
        return data["access"]

    async def recognize(self, image_bytes: bytes) -> Dict[str, Any]:
        """Отправляет картинку на сервер распознавания и возвращает результат."""
        token = await self._get_token()

        form = aiohttp.FormData()
        form.add_field("input_type", "image")
        form.add_field("image", image_bytes,
                       filename="image.jpg",
                       content_type="image/jpeg")

        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.ocr_url,
                data=form,
                headers={"Authorization": f"Bearer {token}"}
            ) as resp:
                if resp.status not in (200, 201):
                    text = await resp.text()
                    raise RuntimeError(f"API error {resp.status}: {text}")
                result = await resp.json()
                # print(f'result: {result}')

        return result
