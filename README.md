# ChinaBot

Telegram bot for China parcel logistics. It works with the same PostgreSQL schema as ChinaSiteCRM and can also run standalone.

## Quick Docker Start

```bash
cp .env-example .env
docker network create china_stack
```

Edit `.env`, then:

```bash
docker compose up -d --build
```

The standalone compose starts PostgreSQL and the bot. The `china_stack` network lets the bot resolve `backend:8000` when ChinaSiteCRM is running on the same VM. On first bot start it creates required tables and the first bot admin from `ADMIN_ID`.

## Run With ChinaSiteCRM

Recommended production layout:

```text
parent/
  ChinaSiteCRM/
  ChinaBot/
```

1. Configure `ChinaSiteCRM/.env`.
2. Configure `ChinaBot/.env`.
3. Make sure `SITE_INTEGRATION_SECRET` is identical in both files.
4. Start from `ChinaSiteCRM`:

```bash
docker compose --profile bot up -d --build
```

In this mode the bot uses the site PostgreSQL container, so site profile and bot data stay in one place. If you start `ChinaBot/docker-compose.yml` separately, keep `SITE_API_URL=http://backend:8000` and make sure the site stack has already created the `china_stack` Docker network.

## Environment Variables

### Telegram

| Variable | Required | Purpose |
|---|---:|---|
| `BOT_TOKEN` | yes | Token from BotFather. |
| `BOT_USERNAME` | recommended | Bot username without `@`; used in profile links. |
| `SHOP_NAME` | yes | Display name in bot messages. |

### PostgreSQL

Historical names are kept for compatibility with the existing code.

| Variable | Required | Purpose |
|---|---:|---|
| `DB_NAME` | yes | PostgreSQL user name, not database name. |
| `DB_PASSWORD` | yes | PostgreSQL password. |
| `DB_IP` | yes | PostgreSQL host. Use `db` for the compose PostgreSQL container, or your external PostgreSQL IP/DNS. |
| `DB_PORT` | yes | PostgreSQL port. |
| `DB_NAME_DATABASE` | yes | PostgreSQL database name. |

### Admins

| Variable | Required | Purpose |
|---|---:|---|
| `ADMIN_ID` | yes | Telegram numeric id of the first bot admin. |
| `ADMIN_NUMBER` | optional | Admin phone saved in the users table. |
| `ADMIN_FORM_CHAT_ID` | optional | Chat where registration forms are sent. |
| `ADMIN_CHAT_ID` | optional | Chat where admin notifications are sent. |

### ChinaSiteCRM Integration

| Variable | Required | Purpose |
|---|---:|---|
| `SITE_API_URL` | recommended | Backend URL. On the same VM/Docker network: `http://backend:8000`. |
| `SITE_INTEGRATION_SECRET` | recommended | Shared secret. Must match ChinaSiteCRM `.env`. |
| `SITE_OUTBOX_ENABLED` | no | `1` to poll site outbox events, `0` to disable. |
| `SITE_OUTBOX_POLL_SECONDS` | no | Poll interval in seconds. |

### Product Recognition

| Variable | Required | Purpose |
|---|---:|---|
| `PRODUCT_RECOGNITION_BASE_URL` | yes for OCR | Sub2API base URL, usually ending with `/v1`. |
| `PRODUCT_RECOGNITION_API_KEY` | yes for OCR | Sub2API API key. |
| `PRODUCT_RECOGNITION_MODEL` | yes for OCR | Model name, for example `gemini-2.5-flash`. |
| `PRODUCT_RECOGNITION_API_MODE` | yes for OCR | `antigravity` uses `/messages`; `chat_completions` uses `/chat/completions`. |
| `PRODUCT_RECOGNITION_TIMEOUT_SECONDS` | no | Recognition request timeout. |

If Sub2API returns `This group does not allow /v1/messages dispatch`, set:

```env
PRODUCT_RECOGNITION_API_MODE=chat_completions
```

### Public Links

| Variable | Purpose |
|---|---|
| `CHANNEL_LINK` | Channel link shown in bot menu. |
| `GUIDE_LINK` | Instruction link shown in bot menu and OCR flow. |
| `SUPPORT_TG` | Support Telegram username. |
| `SUPPORT_EMAIL` | Support email. |
| `SUPPORT_HOURS` | Support working hours text. |

`INSTRUCTION_URL1` was removed because the current code did not use it.

### Rates And Export

| Variable | Purpose |
|---|---|
| `CLEAR_RATE` | Internal cost CNY -> USD rate used in admin calculations. |
| `DEFAULT_RATE` | Client CNY -> USD rate for new users. |
| `YUAN_TO_RUB` | Optional CNY -> RUB rate for Excel export. |
| `YUAN_TO_BYN` | Optional CNY -> BYN rate for expedition Excel export. |
| `CARGO_XLSX_TEMPLATE` | Optional path to custom 352 cargo XLSX template. Relative paths are resolved from the bot project root. |
| `SADOVOD_XLSX_TEMPLATE` | Optional path to custom Sadovod XLSX template. Relative paths are resolved from the bot project root. |
| `EXPEDITION_XLSX_TEMPLATE` | Optional absolute path to custom expedition XLSX template. |

## Local Run Without Docker

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env-example .env
python main.py
```

For Linux/macOS use:

```bash
source venv/bin/activate
cp .env-example .env
python main.py
```

## Database Bootstrap

The bot creates/updates its own tables on startup:

- `users`;
- `cargo_types`;
- `cargos`;
- `items`;
- `cargo_payments`;
- referral tables;
- registration request table when the form flow is used.

It also creates the first admin user from `ADMIN_ID` if no admin exists.

## Useful Commands

```bash
docker compose logs -f bot
docker compose restart bot
docker compose down
```

## Notes

- Do not commit real `.env` files.
- For production with the website, prefer running the bot through the `ChinaSiteCRM` compose profile so both projects share one database.
- If a variable is not listed in `.env-example`, it is not part of the supported deployment surface.
