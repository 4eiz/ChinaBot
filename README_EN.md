<div align="center">

# 🇨🇳 ChinaBot

**Telegram bot for managing parcels from China**

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![aiogram](https://img.shields.io/badge/aiogram-3.x-2CA5E0?style=for-the-badge&logo=telegram&logoColor=white)](https://aiogram.dev)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-asyncpg-336791?style=for-the-badge&logo=postgresql&logoColor=white)](https://postgresql.org)
[![OpenPyXL](https://img.shields.io/badge/Excel-openpyxl-217346?style=for-the-badge&logo=microsoft-excel&logoColor=white)](https://openpyxl.readthedocs.io)
[![ReportLab](https://img.shields.io/badge/PDF-ReportLab-E9173A?style=for-the-badge)](https://reportlab.com)

> A complete management system for shops working with China delivery: item tracking, parcel management, OCR recognition, PDF and Excel export.

</div>

---

## 📋 About

**ChinaBot** is an asynchronous Telegram bot written in Python using the aiogram 3.x framework. It is designed to automate the work of shops and intermediaries dealing with goods delivery from China. The bot supports both customers and administrators within a single unified interface.

The current branch `feature/expedition-excel-export` adds expedition report export in Excel format — **352 (CN→MSK with photos)** and **Sadovod (plain text form)**.

---

## ✨ Features

### 👤 For Customers
- Registration via an in-bot questionnaire form
- Parcel management: create, add items, track statuses
- View balance and payment history
- OCR recognition of product photos with automatic data filling
- Support section with channel link and usage guide

### 🛠️ For Administrators
- Full control over parcels and shipments
- Payment and settlement management (CNY/RUB exchange rate)
- Notifications sent to admin chat
- Report exports:
  - 📄 **PDF Report** — parcel summary with calculations
  - 🧾 **PDF Items** — full item list with photos
  - 📊 **Excel 352** — CN→MSK sheet with product photos
  - 📊 **Excel Sadovod** — plain text expedition form

---

## 🏗️ Architecture

The project follows an **OOP** approach — each module is represented by a class with a clear responsibility boundary.

```
ChinaBot/
├── main.py                         # Entry point, bot startup
├── config.py                       # Configuration, DB connection, Bot instance
├── requirements.txt                # Dependencies
├── .env-example                    # Environment variables example
│
├── app/
│   ├── routers.py                  # All router registrations
│   └── handlers/
│       ├── start.py                # StartHandler — main menu
│       ├── admin/
│       │   ├── exports.py          # AdminExports — PDF & Excel exports
│       │   ├── payments.py         # Payment management
│       │   ├── shipments.py        # Shipment management
│       │   └── fsm.py              # Admin FSM states
│       ├── form/                   # Customer registration form
│       ├── ocr/
│       │   ├── ocr.py              # OCR handler
│       │   └── ocr_fsm.py          # FSM for OCR flow
│       ├── profile/                # User profile
│       └── services/
│           ├── pdf_export.py       # PDFExportService — PDF generation
│           ├── shipment_exporter.py # Excel export (352, Sadovod)
│           ├── admin_notifier.py   # Admin notification service
│           ├── user_notifier.py    # User notification service
│           ├── ocr_parser.py       # OCR response parser
│           └── recognition.py     # Image recognition service
│
├── database/
│   ├── users.py                    # UsersDB — user management
│   ├── orders.py                   # CargoService — parcels & orders
│   └── form.py                     # RequestsDB — registration requests
│
├── keyboards/                      # InlineKeyboard factories
└── media/                          # PhotoBank — media file storage
```

---

## ⚙️ Tech Stack

| Component | Technology | Version |
|-----------|-----------|--------|
| Bot Framework | aiogram | 3.21.0 |
| Database | PostgreSQL + asyncpg | 0.30.0 |
| PDF Generation | ReportLab | 4.4.3 |
| Excel Generation | openpyxl | 3.1.5 |
| Image Processing | Pillow | 11.3.0 |
| Config | python-dotenv | 1.1.1 |
| Language | Python | 3.11+ |

---

## 🚀 Installation & Setup

### 1. Clone the repository

```bash
git clone https://github.com/4eiz/ChinaBot.git
cd ChinaBot
git checkout feature/expedition-excel-export
```

### 2. Create a virtual environment

```bash
python -m venv venv
source venv/bin/activate        # Linux / macOS
venv\Scripts\activate           # Windows
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

Copy `.env-example` to `.env` and fill in all fields:

```bash
cp .env-example .env
```

```env
# Bot token (get from @BotFather)
BOT_TOKEN=

# Shop name displayed to users
SHOP_NAME=

# PostgreSQL connection
DB_NAME=
DB_PASSWORD=
DB_IP=
DB_PORT=
DB_NAME_DATABASE=

# Administrator settings
ADMIN_ID=
ADMIN_NUMBER=
ADMIN_FORM_CHAT_ID=
ADMIN_CHAT_ID=

# External recognition API
PRODUCT_RECOGNITION_BASE_URL=https://sub2api.robcargo.my/v1
PRODUCT_RECOGNITION_API_KEY=
PRODUCT_RECOGNITION_MODEL=gemini-2.5-flash
PRODUCT_RECOGNITION_API_MODE=antigravity
PRODUCT_RECOGNITION_TIMEOUT_SECONDS=45

# Links
CHANNEL_LINK=
GUIDE_LINK=
SUPPORT_TG=
SUPPORT_EMAIL=
SUPPORT_HOURS=

# CNY exchange rate
CLEAR_RATE=
DEFAULT_RATE=0.1898
```

### 5. Run the bot

```bash
python main.py
```

---

## 🗄️ Database

The bot uses **PostgreSQL** with the async driver `asyncpg`. Tables are created automatically on first launch via each DB class's `init()` method.

| Table | Class | Description |
|-------|-------|-------------|
| `users` | `UsersDB` | Users, balance, exchange rate, roles |
| `cargo` / orders | `CargoService` | Parcels, items, shipments, settlements |
| `requests` | `RequestsDB` | Registration requests |

> On first launch, an administrator account is automatically created using `ADMIN_ID` from `.env`.

---

## 📊 Data Export

### PDF Reports
Generated by the `PDFExportService` class (ReportLab):
- **Admin Report** — parcel summary: users, segments, totals
- **Items Report** — each item with photo, description, and price

### Excel Exports (new branch)
Functions `export_cn_msk_goods` and `export_text_form` from `shipment_exporter.py`:
- **Excel 352** — CN→MSK format with product photos embedded in cells
- **Excel Sadovod** — plain text expedition form without photos

---

## 🔐 Security

- All secrets are stored in `.env` and never committed to the repository
- `is_admin` check is performed at the DB level on every request
- Callback handlers are filtered by `AdminFlowCallback` — regular users cannot trigger admin actions

---

## 🤝 Contributing

1. Fork the repository
2. Create a branch: `git checkout -b feature/my-feature`
3. Commit your changes: `git commit -m "feat: add new feature"`
4. Push: `git push origin feature/my-feature`
5. Open a Pull Request

---

<div align="center">

Made with ❤️ for automating China sourcing workflows

</div>
