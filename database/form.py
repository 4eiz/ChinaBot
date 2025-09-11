import asyncpg
import json
from typing import Optional, Literal


class RequestsDB:
    """Работа с таблицей заявок"""
    Status = Literal["pending", "approved", "rejected"]

    REQUIRED_COLUMNS = {
        "id": "SERIAL PRIMARY KEY",
        "user_id": "BIGINT NOT NULL",
        "status": "TEXT DEFAULT 'pending'",
        "data": "TEXT",  # <- теперь строка
        "created_at": "TIMESTAMP DEFAULT NOW()"
    }

    EDITABLE_FIELDS = ["status", "data"]

    def __init__(self, conn: asyncpg.Connection):
        self.conn = conn

    async def init(self):
        await self._create_table()
        await self._add_missing_columns()

    async def _create_table(self):
        cols = ", ".join(f"{c} {t}" for c, t in self.REQUIRED_COLUMNS.items())
        await self.conn.execute(f"""
        CREATE TABLE IF NOT EXISTS requests (
            {cols}
        );
        """)

    async def _add_missing_columns(self):
        existing = await self.conn.fetch("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'requests'
        """)
        existing_cols = {r["column_name"] for r in existing}
        for col, type_ in self.REQUIRED_COLUMNS.items():
            if col not in existing_cols:
                await self.conn.execute(f"ALTER TABLE requests ADD COLUMN {col} {type_};")

    # --- Основное ---
    async def has_active_request(self, user_id: int) -> bool:
        query = """
        SELECT EXISTS(
            SELECT 1 FROM requests
            WHERE user_id = $1 AND status = 'pending'
        )
        """
        return await self.conn.fetchval(query, user_id)

    async def create_request(self, user_id: int, data: dict) -> int:
        """Сохраняем словарь как JSON-строку"""
        json_data = json.dumps(data, ensure_ascii=False)
        query = """
        INSERT INTO requests (user_id, data)
        VALUES ($1, $2)
        RETURNING id
        """
        return await self.conn.fetchval(query, user_id, json_data)

    async def update_status(self, request_id: int, status: Status) -> None:
        query = "UPDATE requests SET status = $1 WHERE id = $2"
        await self.conn.execute(query, status, request_id)

    async def get_request(self, request_id: int) -> Optional[dict]:
        row = await self.conn.fetchrow("SELECT * FROM requests WHERE id = $1", request_id)
        if not row:
            return None
        # Преобразуем обратно в dict
        row_dict = dict(row)
        try:
            row_dict["data"] = json.loads(row_dict["data"]) if row_dict["data"] else {}
        except json.JSONDecodeError:
            row_dict["data"] = {}
        return row_dict

    async def get_last_request_status(self, user_id: int) -> Optional[str]:
        row = await self.conn.fetchrow("""
            SELECT status FROM requests
            WHERE user_id = $1
            ORDER BY created_at DESC
            LIMIT 1
        """, user_id)
        return row["status"] if row else None
