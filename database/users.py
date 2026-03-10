import asyncpg
from typing import Optional

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
        'is_admin': 'BOOLEAN DEFAULT FALSE',
        'created_at': 'TIMESTAMP DEFAULT NOW()',
        
        # --- ДОБАВЛЕННЫЕ КОЛОНКИ ДЛЯ DJANGO ---
        'password': "TEXT DEFAULT ''",               # Автоматически пустой пароль
        'last_login': 'TIMESTAMP DEFAULT NULL',      # Автоматически NULL
        'is_active': 'BOOLEAN DEFAULT TRUE',      # Автоматически NULL
        'is_staff': 'BOOLEAN DEFAULT FALSE',         # Доступ в админку (нет по умолчанию)
        'is_superuser': 'BOOLEAN DEFAULT FALSE'      # Супер-права (нет по умолчанию)
    }

    EDITABLE_FIELDS = ['name', 'surname', 'phone_number', 'source', 'balance', 'rate', 'is_admin']

    def __init__(self, conn: asyncpg.Connection):
        self.conn = conn

    async def init(self):
        await self._create_table_if_not_exists()
        await self._check_and_add_columns()
        await self._setup_defaults()

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

    # ----------------------------- Основная логика -----------------------------

    async def add_user(self, **kwargs):
        """Добавление нового юзера

        :param Атрибуты: name, surname, phone_number, source, rate
        """

        try:
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