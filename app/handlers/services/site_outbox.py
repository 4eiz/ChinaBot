import asyncio
import html
import logging
from typing import Any

import aiohttp
from aiogram import Bot


logger = logging.getLogger(__name__)


class SiteOutboxPoller:
    def __init__(
        self,
        *,
        bot: Bot,
        site_api_url: str,
        integration_secret: str,
        admin_chat_id: str | int | None,
        poll_seconds: int = 10,
        enabled: bool = True,
    ):
        self.bot = bot
        self.site_api_url = (site_api_url or "").rstrip("/")
        self.integration_secret = integration_secret or ""
        self.admin_chat_id = admin_chat_id
        self.poll_seconds = max(int(poll_seconds or 10), 3)
        self.enabled = enabled

    async def run(self):
        if not self.enabled:
            logger.info("Site outbox polling is disabled.")
            return
        if not self.site_api_url or not self.integration_secret:
            logger.warning("Site outbox polling skipped: SITE_API_URL or SITE_INTEGRATION_SECRET is empty.")
            return

        logger.info("Site outbox polling started.")
        while True:
            try:
                await self.poll_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("Site outbox polling failed: %s", exc)
            await asyncio.sleep(self.poll_seconds)

    async def poll_once(self):
        headers = {"X-Site-Integration-Secret": self.integration_secret}
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(f"{self.site_api_url}/api/profile/events/outbox/", params={"limit": 20}) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise RuntimeError(f"outbox fetch failed: {resp.status} {text}")
                payload = await resp.json()

            for event in payload.get("events", []):
                try:
                    await self.handle_event(event)
                    await self.ack(session, event["id"], status="processed")
                except Exception as exc:
                    logger.warning("Failed to handle site event %s: %s", event.get("id"), exc)
                    await self.ack(session, event["id"], status="failed", error=str(exc))

    async def ack(self, session: aiohttp.ClientSession, event_id: int, *, status: str, error: str | None = None):
        async with session.post(
            f"{self.site_api_url}/api/profile/events/outbox/{event_id}/ack/",
            json={"status": status, "error": error or ""},
        ) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise RuntimeError(f"outbox ack failed: {resp.status} {text}")

    async def handle_event(self, event: dict[str, Any]):
        if not self.admin_chat_id:
            return
        text = self.format_event(event)
        if text:
            await self.bot.send_message(chat_id=self.admin_chat_id, text=text, parse_mode="HTML")

    def format_event(self, event: dict[str, Any]) -> str:
        event_type = event.get("event_type") or "profile.event"
        payload = event.get("payload") or {}
        user = payload.get("user") or {}
        cargo = payload.get("cargo") or {}
        item = payload.get("item") or {}
        media = payload.get("media") or {}

        user_line = self.user_line(user, event.get("user_id"))
        cargo_line = self.cargo_line(cargo, event.get("cargo_id"))

        if event_type == "profile.item_created":
            return (
                "🆕 <b>Товар добавлен на сайте</b>\n"
                f"{user_line}\n{cargo_line}\n"
                f"🛍 <b>{self.esc(item.get('title') or 'Товар')}</b> "
                f"× <code>{self.esc(item.get('quantity') or '')}</code>\n"
                f"💵 <code>{self.esc(item.get('price') or '0')}¥</code> · "
                f"⚖️ <code>{self.esc(item.get('weight_kg') or '0')} кг</code>"
            )
        if event_type == "profile.item_updated":
            return (
                "✏️ <b>Товар обновлён на сайте</b>\n"
                f"{user_line}\n{cargo_line}\n"
                f"🛍 <b>{self.esc(item.get('title') or 'Товар')}</b>"
            )
        if event_type == "profile.item_removed":
            return (
                "🗑 <b>Товар удалён на сайте</b>\n"
                f"{user_line}\n{cargo_line}\n"
                f"🛍 <b>{self.esc(item.get('title') or 'Товар')}</b>"
            )
        if event_type == "profile.cargo_created":
            return f"📦 <b>Личная посылка создана на сайте</b>\n{user_line}\n{cargo_line}"
        if event_type == "profile.cargo_updated":
            return f"✏️ <b>Посылка обновлена на сайте</b>\n{user_line}\n{cargo_line}"
        if event_type == "profile.user_updated":
            return f"👤 <b>Профиль обновлён на сайте</b>\n{user_line}"
        if event_type == "profile.media_uploaded":
            return (
                "🖼 <b>Фото загружено на сайте</b>\n"
                f"{user_line}\n"
                f"Файл: <code>{self.esc(media.get('original_name') or media.get('photo_file_id') or '')}</code>"
            )
        return f"🔔 <b>Событие сайта</b>: <code>{self.esc(event_type)}</code>\n{user_line}"

    def user_line(self, user: dict[str, Any], fallback_id: Any) -> str:
        user_id = user.get("user_id") or fallback_id or "?"
        name = " ".join(filter(None, [user.get("name"), user.get("surname")])).strip() or f"ID {user_id}"
        return f"👤 <b>{self.esc(name)}</b> · <code>{self.esc(user_id)}</code>"

    def cargo_line(self, cargo: dict[str, Any], fallback_id: Any) -> str:
        cargo_id = cargo.get("cargo_id") or fallback_id
        if not cargo_id:
            return "📦 <code>Без посылки</code>"
        title = cargo.get("title") or "Посылка"
        return f"📦 <b>#{self.esc(cargo_id)} {self.esc(title)}</b>"

    @staticmethod
    def esc(value: Any) -> str:
        return html.escape(str(value), quote=True)
