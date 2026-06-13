import asyncpg
from typing import Optional
from decimal import Decimal, InvalidOperation

from config import ADMIN_ID, ADMIN_NUMBER, DEFAULT_RATE

class UsersDB:
    """Класс для работы с юзером

    :param init(): - Первоночальная настройка
    :param add_user(): - Добавление нового юзера
    :param update_user(): - Обновление поля юзера
    :param delete_user(): - Удаления юзера
    :param is_admin(): - Проверка статуса админа
    :param get_user(): - Получение юзера
    """

    default_rate = str(DEFAULT_RATE)

    REQUIRED_COLUMNS = {
        'id': 'BIGINT PRIMARY KEY',
        'name': 'TEXT',
        'surname': 'TEXT',
        'phone_number': 'TEXT',
        'source': 'TEXT',
        'balance': 'NUMERIC DEFAULT 0',
        'rate': f'NUMERIC DEFAULT {default_rate}',
        'rate_locked': 'BOOLEAN DEFAULT FALSE',
        'is_admin': 'BOOLEAN DEFAULT FALSE',
        'created_at': 'TIMESTAMP DEFAULT NOW()',
        
        # --- ДОБАВЛЕННЫЕ КОЛОНКИ ДЛЯ DJANGO ---
        'password': "TEXT DEFAULT ''",               # Автоматически пустой пароль
        'last_login': 'TIMESTAMP DEFAULT NULL',      # Автоматически NULL
        'is_active': 'BOOLEAN DEFAULT TRUE',      # Автоматически NULL
        'is_staff': 'BOOLEAN DEFAULT FALSE',         # Доступ в админку (нет по умолчанию)
        'is_superuser': 'BOOLEAN DEFAULT FALSE'      # Супер-права (нет по умолчанию)
    }

    EDITABLE_FIELDS = ['name', 'surname', 'phone_number', 'source', 'balance', 'rate', 'rate_locked', 'is_admin']

    def __init__(self, conn: asyncpg.Connection):
        self.conn = conn

    @staticmethod
    def _normalize_phone(value: str | None) -> str | None:
        raw = str(value or '').strip()
        if not raw:
            return raw
        digits = ''.join(ch for ch in raw if ch.isdigit())
        return f'+{digits}' if digits else (raw if raw.startswith('+') else f'+{raw}')

    async def get_default_rate(self) -> Decimal:
        try:
            value = await self.conn.fetchval(
                "SELECT value FROM site_settings WHERE key = 'users.default_rate' LIMIT 1"
            )
            if value not in (None, ''):
                return Decimal(str(value))
        except Exception:
            pass
        return DEFAULT_RATE

    async def init(self):
        await self._create_table_if_not_exists()
        await self._check_and_add_columns()
        await self._setup_defaults()
        await self._create_referral_tables_if_not_exists()

    # ----------------------------- Первоначальная настройка -----------------------------

    async def _create_table_if_not_exists(self):
        """
        Создание таблицы
        """

        cols = ', '.join([f'{col} {type_}' for col, type_ in self.REQUIRED_COLUMNS.items()])
        await self.conn.execute(f"""
        CREATE TABLE IF NOT EXISTS users (
            {cols}
        )
        """)

    async def _check_and_add_columns(self):
        """
        Проверка и добавление новых колонн
        """

        existing = await self.conn.fetch("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'users'
        """)
        existing_cols = {row['column_name'] for row in existing}

        for col, type_ in self.REQUIRED_COLUMNS.items():
            if col not in existing_cols:
                print(f"Добавляем колонку: {col}")
                await self.conn.execute(f"""
                ALTER TABLE users ADD COLUMN {col} {type_}
                """)


    async def _setup_defaults(self):
        """
        Установка начальных настроек
        """

        admin_exists = await self.conn.fetchval("SELECT EXISTS (SELECT 1 FROM users WHERE is_admin = TRUE)")
        if not admin_exists:
            print(f"Создаю админа по умолчанию (id = {ADMIN_ID})")
            query = f"""
            INSERT INTO users (id, name, surname, phone_number, balance, is_admin)
            VALUES ({ADMIN_ID}, 'Администратор', '', '{ADMIN_NUMBER}', 0, TRUE)
            ON CONFLICT (id) DO NOTHING
            """

            await self.conn.execute(query=query)

    async def _create_referral_tables_if_not_exists(self):
        await self.conn.execute("""
        CREATE TABLE IF NOT EXISTS user_referrals (
            id BIGSERIAL PRIMARY KEY,
            referrer_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            invited_id BIGINT NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
            source TEXT NULL,
            note TEXT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS referral_transactions (
            id BIGSERIAL PRIMARY KEY,
            referral_id BIGINT NULL REFERENCES user_referrals(id) ON DELETE SET NULL,
            user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            kind TEXT NOT NULL DEFAULT 'earned',
            amount_usd NUMERIC(12, 2) NOT NULL DEFAULT 0,
            note TEXT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        );

        CREATE INDEX IF NOT EXISTS user_referrals_referrer_idx ON user_referrals(referrer_id);
        CREATE INDEX IF NOT EXISTS referral_transactions_user_idx ON referral_transactions(user_id);
        CREATE INDEX IF NOT EXISTS referral_transactions_kind_idx ON referral_transactions(kind);
        """)
        await self.conn.execute("""
        ALTER TABLE referral_transactions
        ADD COLUMN IF NOT EXISTS cargo_id BIGINT NULL;

        CREATE INDEX IF NOT EXISTS referral_transactions_cargo_idx
        ON referral_transactions(cargo_id);
        """)

    # ----------------------------- Основная логика -----------------------------

    async def add_user(self, **kwargs):
        """Добавление нового юзера

        :param Атрибуты: name, surname, phone_number, source, rate
        """

        try:
            if 'phone_number' in kwargs:
                kwargs['phone_number'] = self._normalize_phone(kwargs.get('phone_number'))
            if 'rate' not in kwargs or kwargs.get('rate') in (None, ''):
                kwargs['rate'] = await self.get_default_rate()

            fields = [k for k in kwargs.keys() if k in self.REQUIRED_COLUMNS]
            values = [kwargs[k] for k in fields]

            fields_sql = ", ".join(fields)
            placeholders = ", ".join(f"${i+1}" for i in range(len(values)))
            updates = ", ".join(f"{field} = EXCLUDED.{field}" for field in fields if field != "id")

            query = f"""
            INSERT INTO users ({fields_sql})
            VALUES ({placeholders})
            ON CONFLICT (id) DO UPDATE SET
                {updates}
            """

            await self.conn.execute(query, *values)

            return True
        
        except Exception as e:
            # ТУТ БУДЕТ ЛОГИРОВАНИЕ
            return False


    async def update_user(self, user_id: int, updates: dict):
        """
        Обновление информации об юзере
        
        :param name: str
        :param surname: str 
        :param phone_number: str
        :param source: str
        :param balance: float
        :param rate: float
        :param is_admin: bool
        """

        for field in updates:
            if field not in self.EDITABLE_FIELDS:
                raise ValueError(f"Недопустимое поле: {field}")

        if 'phone_number' in updates:
            updates['phone_number'] = self._normalize_phone(updates.get('phone_number'))
        if 'rate' in updates:
            try:
                updates['rate'] = Decimal(str(updates['rate']))
            except (InvalidOperation, TypeError):
                raise ValueError("Некорректный курс")

        set_clause = ", ".join(f"{field} = ${i+2}" for i, field in enumerate(updates))
        values = list(updates.values())

        query = f"UPDATE users SET {set_clause} WHERE id = $1"
        await self.conn.execute(query, user_id, *values)


    async def delete_user(self, user_id: int):
        """
        Удаление юзера

        :param user_id: ID пользователя

        :return result: bool
        """

        result = await self.conn.execute("DELETE FROM users WHERE id = $1", user_id)
        return bool(result)


    async def is_admin(self, user_id: int) -> Optional[bool]:
        """
        Проверка статуса администратора.

        :param user_id: ID пользователя
        :return: True если админ, False если нет, None если пользователь не найден
        """
        result = await self.conn.fetchval("SELECT is_admin FROM users WHERE id = $1", user_id)
        if result is None:
            return None
        return bool(result)



    async def get_user(self, user_id: int) -> Optional[dict]:
        """
        Получение данных юзера

        :param user_id: ID пользователя

        :return result: dict если найден юзер, None если юзер не найден
        """
    
        row = await self.conn.fetchrow("SELECT * FROM users WHERE id = $1", user_id)
        return dict(row) if row else None

    async def create_referral_relationship(
        self,
        *,
        referrer_id: int,
        invited_id: int,
        source: str = "bot_link",
        note: str | None = None,
    ) -> bool:
        if not referrer_id or not invited_id or int(referrer_id) == int(invited_id):
            return False

        await self._create_referral_tables_if_not_exists()
        result = await self.conn.execute("""
        INSERT INTO user_referrals (referrer_id, invited_id, source, note)
        SELECT $1, $2, $3, $4
        WHERE EXISTS (SELECT 1 FROM users WHERE id = $1)
          AND EXISTS (SELECT 1 FROM users WHERE id = $2)
        ON CONFLICT (invited_id) DO NOTHING
        """, int(referrer_id), int(invited_id), source, note)
        return result.endswith("1")

    async def get_referral_overview(self, user_id: int) -> dict:
        await self._create_referral_tables_if_not_exists()
        invited_count = await self.conn.fetchval(
            "SELECT COUNT(*) FROM user_referrals WHERE referrer_id = $1",
            user_id,
        )
        totals = await self.conn.fetchrow("""
        SELECT
            COALESCE(SUM(amount_usd) FILTER (WHERE kind = 'earned'), 0) AS earned,
            COALESCE(SUM(amount_usd) FILTER (WHERE kind = 'paid'), 0) AS paid,
            COALESCE(SUM(amount_usd) FILTER (WHERE kind = 'adjustment'), 0) AS adjustment
        FROM referral_transactions
        WHERE user_id = $1
        """, user_id)
        earned = Decimal(str(totals["earned"] or 0))
        paid = Decimal(str(totals["paid"] or 0))
        adjustment = Decimal(str(totals["adjustment"] or 0))
        return {
            "invited_count": int(invited_count or 0),
            "earned": earned,
            "paid": paid,
            "balance": (earned + adjustment - paid).quantize(Decimal("0.01")),
        }
