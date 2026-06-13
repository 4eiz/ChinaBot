<div align="center">

# 🇨🇳 ChinaBot

**Telegram-бот для управления посылками из Китая**

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![aiogram](https://img.shields.io/badge/aiogram-3.x-2CA5E0?style=for-the-badge&logo=telegram&logoColor=white)](https://aiogram.dev)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-asyncpg-336791?style=for-the-badge&logo=postgresql&logoColor=white)](https://postgresql.org)
[![OpenPyXL](https://img.shields.io/badge/Excel-openpyxl-217346?style=for-the-badge&logo=microsoft-excel&logoColor=white)](https://openpyxl.readthedocs.io)
[![ReportLab](https://img.shields.io/badge/PDF-ReportLab-E9173A?style=for-the-badge)](https://reportlab.com)

> Полноценная система для магазинов, работающих с доставкой из Китая: учёт товаров, управление посылками, OCR-распознавание, экспорт в PDF и Excel.

</div>

---

## 📋 О проекте

**ChinaBot** — асинхронный Telegram-бот, написанный на Python с использованием фреймворка aiogram 3.x. Предназначен для автоматизации работы магазинов и посредников, занимающихся доставкой товаров из Китая. Бот поддерживает работу с клиентами и администраторами в едином интерфейсе.

Текущая ветка `feature/expedition-excel-export` добавляет экспорт экспедиционных отчётов в формате Excel — **352 (CN→MSK с фото)** и **Садовод (текстовый бланк)**.

---

## ✨ Возможности

### 👤 Для клиентов
- Регистрация через форму-анкету прямо в боте
- Управление посылками: создание, добавление товаров, отслеживание статусов
- Просмотр баланса и истории оплат
- OCR-распознавание фото товаров с автоматическим заполнением данных
- Поддержка и информационный раздел с ссылками на канал и инструкции

### 🛠️ Для администраторов
- Полный контроль над посылками и отправками
- Управление платежами и расчётами (курс CNY/RUB)
- Уведомления в чат администратора
- Экспорт отчётов:
  - 📄 **PDF-отчёт** — сводка по посылке с расчётами
  - 🧾 **PDF-товары** — список всех товаров с фотографиями
  - 📊 **Excel 352** — лист CN→MSK с фото товаров
  - 📊 **Excel Садовод** — текстовый экспедиционный бланк

---

## 🏗️ Архитектура

Проект построен по принципу **ООП** — каждый модуль представлен классом с чёткой зоной ответственности.

```
ChinaBot/
├── main.py                         # Точка входа, запуск бота
├── config.py                       # Конфигурация, подключение к БД, Bot instance
├── requirements.txt                # Зависимости
├── .env-example                    # Пример переменных окружения
│
├── app/
│   ├── routers.py                  # Регистрация всех роутеров
│   └── handlers/
│       ├── start.py                # StartHandler — главное меню
│       ├── admin/
│       │   ├── exports.py          # AdminExports — PDF и Excel экспорты
│       │   ├── payments.py         # Управление платежами
│       │   ├── shipments.py        # Управление отправками
│       │   └── fsm.py              # FSM-состояния админки
│       ├── form/                   # Регистрационная форма клиента
│       ├── ocr/
│       │   ├── ocr.py              # OCR-обработчик
│       │   └── ocr_fsm.py          # FSM для OCR-процесса
│       ├── profile/                # Профиль пользователя
│       └── services/
│           ├── pdf_export.py       # PDFExportService — генерация PDF
│           ├── shipment_exporter.py # Excel-экспорт (352, Садовод)
│           ├── admin_notifier.py   # Уведомления администраторам
│           ├── user_notifier.py    # Уведомления пользователям
│           ├── ocr_parser.py       # Парсинг OCR-ответов
│           └── recognition.py     # Сервис распознавания изображений
│
├── database/
│   ├── users.py                    # UsersDB — работа с пользователями
│   ├── orders.py                   # CargoService — посылки и заказы
│   └── form.py                     # RequestsDB — заявки на регистрацию
│
├── keyboards/                      # InlineKeyboard-фабрики
└── media/                          # PhotoBank — хранение медиа-файлов
```

---

## ⚙️ Технологии

| Компонент | Технология | Версия |
|-----------|-----------|--------|
| Фреймворк бота | aiogram | 3.21.0 |
| База данных | PostgreSQL + asyncpg | 0.30.0 |
| Генерация PDF | ReportLab | 4.4.3 |
| Генерация Excel | openpyxl | 3.1.5 |
| Изображения | Pillow | 11.3.0 |
| Конфиг | python-dotenv | 1.1.1 |
| Язык | Python | 3.11+ |

---

## 🚀 Установка и запуск

### 1. Клонирование репозитория

```bash
git clone https://github.com/4eiz/ChinaBot.git
cd ChinaBot
git checkout feature/expedition-excel-export
```

### 2. Создание виртуального окружения

```bash
python -m venv venv
source venv/bin/activate        # Linux / macOS
venv\Scripts\activate           # Windows
```

### 3. Установка зависимостей

```bash
pip install -r requirements.txt
```

### 4. Настройка переменных окружения

Скопируйте `.env-example` в `.env` и заполните все поля:

```bash
cp .env-example .env
```

```env
# Bot token (получить у @BotFather)
BOT_TOKEN=

# Название магазина
SHOP_NAME=

# PostgreSQL
DB_NAME=
DB_PASSWORD=
DB_IP=
DB_PORT=
DB_NAME_DATABASE=

# Администратор
ADMIN_ID=
ADMIN_NUMBER=
ADMIN_FORM_CHAT_ID=
ADMIN_CHAT_ID=

# Внешний API (распознавание)
PRODUCT_RECOGNITION_BASE_URL=https://sub2api.robcargo.my/v1
PRODUCT_RECOGNITION_API_KEY=
PRODUCT_RECOGNITION_MODEL=gemini-2.5-flash
PRODUCT_RECOGNITION_API_MODE=antigravity
PRODUCT_RECOGNITION_TIMEOUT_SECONDS=45

# Ссылки
CHANNEL_LINK=
GUIDE_LINK=
SUPPORT_TG=
SUPPORT_EMAIL=
SUPPORT_HOURS=

# Курс юаня
CLEAR_RATE=
DEFAULT_RATE=0.1898
```

### 5. Запуск

```bash
python main.py
```

---

## 🗄️ База данных

Бот использует **PostgreSQL** с асинхронным драйвером `asyncpg`. Таблицы создаются автоматически при первом запуске через методы `init()` каждого DB-класса.

| Таблица | Класс | Описание |
|---------|-------|----------|
| `users` | `UsersDB` | Пользователи, баланс, курс, роли |
| `cargo` / заказы | `CargoService` | Посылки, товары, отправки, расчёты |
| `requests` | `RequestsDB` | Заявки на регистрацию |

> При первом запуске автоматически создаётся администратор с `ADMIN_ID` из `.env`.

---

## 📊 Экспорт данных

### PDF-отчёты
Генерируются классом `PDFExportService` (ReportLab):
- **Админ-отчёт** — сводка по посылке: пользователи, сегменты, суммы
- **Отчёт по товарам** — каждый товар с фото, описанием, ценой

### Excel-экспорты (новая ветка)
Функции `export_cn_msk_goods` и `export_text_form` из `shipment_exporter.py`:
- **Excel 352** — формат CN→MSK, включает фотографии товаров, вставленные в ячейки
- **Excel Садовод** — текстовый экспедиционный бланк без фото

---

## 🔐 Безопасность

- Все секреты хранятся в `.env` и никогда не попадают в репозиторий
- Проверка `is_admin` выполняется на уровне БД при каждом запросе
- Callback-хендлеры фильтруются по `AdminFlowCallback` — обычный пользователь не может вызвать admin-действия

---

## 🤝 Вклад в проект

1. Форкните репозиторий
2. Создайте ветку: `git checkout -b feature/my-feature`
3. Закоммитьте изменения: `git commit -m "feat: добавил новую функцию"`
4. Сделайте push: `git push origin feature/my-feature`
5. Откройте Pull Request

---

<div align="center">

Сделано с ❤️ для автоматизации работы с Китаем

</div>
