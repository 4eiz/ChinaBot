import json
import asyncpg

from typing import Optional, Dict, Any, List, Tuple
from decimal import Decimal, ROUND_UP, ROUND_HALF_UP

from collections import defaultdict
from .users import UsersDB

from config import CLEAR_RATE, DEFAULT_RATE


# --------------------------- Cargo Types ---------------------------

class CargoTypesDB:
    """Справочник типов груза (тарифы USD/кг)."""

    REQUIRED_COLUMNS = {
        'id': 'BIGSERIAL PRIMARY KEY',
        'code': "TEXT UNIQUE",
        'name': "TEXT NOT NULL",
        'rate_per_kg_usd': "NUMERIC(10,2) NOT NULL",
        'is_active': "BOOLEAN NOT NULL DEFAULT TRUE",
        'sort_order': "INT NOT NULL DEFAULT 0",
        'comment': "TEXT",
        'created_at': 'TIMESTAMP DEFAULT NOW()',
        'updated_at': 'TIMESTAMP DEFAULT NOW()'
    }

    def __init__(self, *, conn: asyncpg.Connection):
        self.conn = conn

    async def init(self) -> None:
        cols = ', '.join(f"{c} {t}" for c, t in self.REQUIRED_COLUMNS.items())
        await self.conn.execute(f"CREATE TABLE IF NOT EXISTS cargo_types ({cols})")
        await self._seed_defaults()

    async def get(self, *, cargo_type_id: int) -> dict | None:
        row = await self.conn.fetchrow(
            "SELECT * FROM cargo_types WHERE id = $1",
            cargo_type_id
        )
        return dict(row) if row else None

    async def _seed_defaults(self) -> None:
        exists = await self.conn.fetchval("SELECT EXISTS (SELECT 1 FROM cargo_types)")
        if exists:
            return
        defaults = [
            ('clothes', 'Одежда', Decimal('7.50')),
            ('shoes', 'Обувь', Decimal('7.00')),
            ('household', 'Хозтовары', Decimal('6.00')),
            ('mixed', 'Смешанный', Decimal('7.50')),
        ]
        for code, name, rate in defaults:
            await self.conn.execute(
                """
                INSERT INTO cargo_types(code, name, rate_per_kg_usd)
                VALUES ($1, $2, $3)
                ON CONFLICT (code) DO NOTHING
                """,
                code, name, rate
            )

    async def get_id_by_code(self, *, code: str) -> Optional[int]:
        return await self.conn.fetchval("SELECT id FROM cargo_types WHERE code=$1", code)

    async def list_active(self) -> List[dict]:
        rows = await self.conn.fetch(
            "SELECT * FROM cargo_types WHERE is_active ORDER BY sort_order, id"
        )
        return [dict(r) for r in rows]
    
    async def get_name_by_id(self, *, cargo_type_id: int) -> Optional[str]:
        row = await self.conn.fetchrow(
            "SELECT name FROM cargo_types WHERE id=$1",
            cargo_type_id
        )
        return row["name"] if row else None


# ------------------------------ Cargos ------------------------------

class CargosDB:
    """Грузы (общие/личные)."""

    REQUIRED_COLUMNS = {
        'id': 'BIGSERIAL PRIMARY KEY',
        'scope': "TEXT NOT NULL",                     # 'shared' | 'personal'
        'owner_user_id': "BIGINT",                    # NULL для shared
        'cargo_type_id': "BIGINT NOT NULL",           # FK cargo_types.id
        'status': "TEXT NOT NULL DEFAULT 'open'",     # open|closed (редактируемость)
        'payment_status': "TEXT NOT NULL DEFAULT 'unpaid'",   # unpaid|awaiting_payment|partial|paid
        'route_status': "TEXT NOT NULL DEFAULT 'created'",    # created|to_moscow|in_moscow|to_brest|in_brest|delivered
        'title': "TEXT",
        'total_weight_kg': "NUMERIC(10,3) NOT NULL DEFAULT 0",
        'items_count': "INT NOT NULL DEFAULT 0",
        'rate_cn_to_msk_usd': "NUMERIC(10,2)",        # тариф $/кг плечо 1
        'rate_msk_to_by_usd': "NUMERIC(10,2)",        # тариф $/кг плечо 2
        'created_at': 'TIMESTAMP DEFAULT NOW()',
        'updated_at': 'TIMESTAMP DEFAULT NOW()'
    }

    def __init__(self, *, conn: asyncpg.Connection):
        self.conn = conn

    async def init(self) -> None:
        cols = ', '.join(f"{c} {t}" for c, t in self.REQUIRED_COLUMNS.items())
        await self.conn.execute(f"CREATE TABLE IF NOT EXISTS cargos ({cols})")
        await self._check_and_add_columns()

    async def _check_and_add_columns(self) -> None:
        rows = await self.conn.fetch("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'cargos'
        """)
        existing_cols = {r['column_name'] for r in rows}
        for col, typ in self.REQUIRED_COLUMNS.items():
            if col not in existing_cols:
                await self.conn.execute(f"ALTER TABLE cargos ADD COLUMN {col} {typ}")

    async def create(self, *, scope: str, cargo_type_id: int,
                     owner_user_id: Optional[int] = None,
                     title: Optional[str] = None) -> dict:
        row = await self.conn.fetchrow(
            """
            INSERT INTO cargos(scope, owner_user_id, cargo_type_id, title)
            VALUES ($1, $2, $3, $4) RETURNING *
            """,
            scope, owner_user_id, cargo_type_id, title
        )
        return dict(row)

    async def get(self, *, cargo_id: int) -> Optional[dict]:
        row = await self.conn.fetchrow("SELECT * FROM cargos WHERE id=$1", cargo_id)
        return dict(row) if row else None

    async def find_or_create_open_shared(self, *, cargo_type_id: int) -> dict:
        row = await self.conn.fetchrow(
            """
            SELECT * FROM cargos
            WHERE scope='shared' AND status='open' AND cargo_type_id=$1
            LIMIT 1
            """,
            cargo_type_id
        )
        if row:
            return dict(row)
        return await self.create(scope='shared', cargo_type_id=cargo_type_id)

    async def find_or_create_open_personal(self, *, user_id: int, cargo_type_id: int) -> dict:
        row = await self.conn.fetchrow(
            """
            SELECT * FROM cargos
            WHERE scope='personal' AND status='open' AND owner_user_id=$1 AND cargo_type_id=$2
            LIMIT 1
            """,
            user_id, cargo_type_id
        )
        if row:
            return dict(row)
        return await self.create(scope='personal', cargo_type_id=cargo_type_id, owner_user_id=user_id)

    async def recalc_weight_and_count(self, *, cargo_id: int) -> None:
        agg = await self.conn.fetchrow(
            """
            SELECT COALESCE(SUM(weight_kg * quantity), 0) AS total_weight_kg,
                   COUNT(*) AS items_count
            FROM items WHERE cargo_id=$1
            """,
            cargo_id
        )
        await self.conn.execute(
            """
            UPDATE cargos
            SET total_weight_kg=$2, items_count=$3, updated_at=NOW()
            WHERE id=$1
            """,
            cargo_id, agg['total_weight_kg'], agg['items_count']
        )

    async def compute_pricing(self, *, cargo_id: int) -> dict:
        """Расчёт доставки по максимальному тарифу типов внутри груза."""
        cargo = await self.get(cargo_id=cargo_id)
        if not cargo:
            raise ValueError("Груз не найден")

        total_weight = Decimal(str(cargo['total_weight_kg'] or 0))
        if total_weight <= 0:
            await self.recalc_weight_and_count(cargo_id=cargo_id)
            cargo = await self.get(cargo_id=cargo_id)
            total_weight = Decimal(str(cargo['total_weight_kg'] or 0))

        rows = await self.conn.fetch(
            """
            SELECT DISTINCT t.rate_per_kg_usd
            FROM items i
            JOIN cargo_types t ON t.id = i.item_type_id
            WHERE i.cargo_id=$1
            """,
            cargo_id
        )
        rate = Decimal('0.00')
        if rows:
            rate = max(Decimal(str(r['rate_per_kg_usd'])) for r in rows)

        # Округление до 0.1 кг и минимум 5 кг
        step = Decimal('0.1')
        chargeable = (total_weight / step).to_integral_value(rounding=ROUND_UP) * step
        # if chargeable < Decimal('5.0'):
        #     chargeable = Decimal('5.0')

        delivery_cost = (chargeable * rate).quantize(Decimal('0.01'), rounding=ROUND_UP)
        return {
            'total_weight_kg': float(total_weight),
            'chargeable_weight_kg': float(chargeable),
            'rate_per_kg_usd': float(rate),
            'delivery_cost_usd': float(delivery_cost),
        }


    async def set_cargo_type(self, *, cargo_id: int, cargo_type_id: int) -> None:
        await self.conn.execute(
            "UPDATE cargos SET cargo_type_id=$2, updated_at=NOW() WHERE id=$1",
            cargo_id, cargo_type_id
        )


    async def get_name_by_id(self, *, cargo_type_id: int) -> Optional[str]:
        row = await self.conn.fetchrow(
            "SELECT name FROM cargo_types WHERE id=$1",
            cargo_type_id
        )
        return row["name"] if row else None
    
    async def list_by_user(self, *, user_id: int) -> List[dict]:
        rows = await self.conn.fetch(
            """
            SELECT * FROM cargos
            WHERE owner_user_id=$1
            ORDER BY created_at DESC
            """,
            user_id
        )
        return [dict(r) for r in rows]


    async def count_by_user(self, *, user_id: int) -> int:
        return await self.conn.fetchval(
            "SELECT COUNT(*) FROM cargos WHERE owner_user_id=$1",
            user_id
        )
    
    async def list_open_personal_by_user(self, *, user_id: int) -> list[dict]:
        rows = await self.conn.fetch(
            """
            SELECT * FROM cargos
            WHERE scope='personal' AND status='open' AND owner_user_id=$1
            ORDER BY created_at DESC, id DESC
            """,
            user_id
        )
        return [dict(r) for r in rows]
    
    async def list_shared_by_user_participation(self, *, user_id: int) -> List[dict]:
        rows = await self.conn.fetch(
            """
            SELECT DISTINCT c.*
            FROM cargos c
            JOIN items i ON i.cargo_id = c.id
            WHERE c.scope='shared' AND i.user_id=$1
            ORDER BY c.created_at DESC, c.id DESC
            """,
            user_id
        )
        return [dict(r) for r in rows]
    
    async def set_status(self, *, cargo_id: int, status: str) -> None:
        await self.conn.execute(
            "UPDATE cargos SET status=$2, updated_at=NOW() WHERE id=$1",
            cargo_id, status
        )

    async def set_payment_status(self, *, cargo_id: int, status: str) -> None:
        await self.conn.execute(
            "UPDATE cargos SET payment_status=$2, updated_at=NOW() WHERE id=$1",
            cargo_id, status
        )

    async def set_route_status(self, *, cargo_id: int, status: str) -> None:
        await self.conn.execute(
            "UPDATE cargos SET route_status=$2, updated_at=NOW() WHERE id=$1",
            cargo_id, status
        )

    async def set_delivery_rates(
        self,
        *,
        cargo_id: int,
        rate_cn_to_msk_usd: Optional[Decimal],
        rate_msk_to_by_usd: Optional[Decimal]
    ) -> None:
        await self.conn.execute(
            """
            UPDATE cargos
            SET rate_cn_to_msk_usd=$2, rate_msk_to_by_usd=$3, updated_at=NOW()
            WHERE id=$1
            """,
            cargo_id, rate_cn_to_msk_usd, rate_msk_to_by_usd
        )

    async def list_all(self) -> list[dict]:
        rows = await self.conn.fetch("SELECT * FROM cargos ORDER BY created_at DESC")
        return [dict(r) for r in rows]


# ------------------------------ Items ------------------------------

class ItemsDB:
    REQUIRED_COLUMNS = {
        'id': 'BIGSERIAL PRIMARY KEY',
        'user_id': 'BIGINT NOT NULL',
        'cargo_id': 'BIGINT',
        'item_type_id': 'BIGINT NOT NULL',
        'title': 'TEXT NOT NULL',
        'photo_file_id': 'TEXT',
        'price': 'NUMERIC(12,2) NOT NULL DEFAULT 0',
        'quantity': 'INT NOT NULL DEFAULT 1',
        'weight_kg': 'NUMERIC(10,3) NOT NULL DEFAULT 0',
        'cn_domestic_shipping': 'NUMERIC(12,2) NOT NULL DEFAULT 0',
        'color': 'TEXT',
        'size': 'TEXT',
        'source_url': 'TEXT',
        'extra': "JSONB NOT NULL DEFAULT '{}'::jsonb",
        'created_at': 'TIMESTAMP DEFAULT NOW()',
        'updated_at': 'TIMESTAMP DEFAULT NOW()'
    }

    def __init__(self, *, conn: asyncpg.Connection):
        self.conn = conn

    async def init(self) -> None:
        columns_sql = ', '.join(f"{col} {typ}" for col, typ in self.REQUIRED_COLUMNS.items())
        await self.conn.execute(f"CREATE TABLE IF NOT EXISTS items ({columns_sql})")

    async def add(
        self,
        *,
        cargo_id: Optional[int],
        user_id: int,
        item_type_id: int,
        title: str,
        photo_file_id: Optional[str],
        price,
        quantity: int,
        weight_kg=0,
        cn_domestic_shipping=0,
        color: Optional[str],
        size: Optional[str],
        source_url: Optional[str],
        extra: Optional[Dict[str, Any]] = None,   # ← dict
    ) -> asyncpg.Record:
        sql = """
        INSERT INTO items (
            cargo_id, user_id, item_type_id, title, photo_file_id, price, quantity,
            weight_kg, cn_domestic_shipping, color, size, source_url, extra
        )
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13::jsonb)
        RETURNING *;
        """
        return await self.conn.fetchrow(
            sql,
            cargo_id, user_id, item_type_id, title, photo_file_id, price, quantity,
            weight_kg, cn_domestic_shipping, color, size, source_url,
            extra or {},  # ← dict, кодек сам сериализует
        )

    async def add_from_dict(
        self,
        *,
        cargo_id: Optional[int],
        user_id: int,
        item_type_id: int,
        data: Dict[str, Any],
    ) -> asyncpg.Record:
        title = data.get("title") or data.get("name") or "Без названия"
        price = data.get("price")
        quantity = int(data.get("quantity") or 1)
        weight_kg = data.get("weight_kg") or 0
        cn_domestic_shipping = data.get("cn_domestic_shipping") or 0
        color = data.get("color")
        size = data.get("size")
        photo_file_id = data.get("photo_file_id")
        source_url = data.get("source_url")
        extra = data.get("extra")  # ← может быть dict

        return await self.add(
            cargo_id=cargo_id,
            user_id=user_id,
            item_type_id=item_type_id,
            title=title,
            photo_file_id=photo_file_id,
            price=price,
            quantity=quantity,
            weight_kg=weight_kg,
            cn_domestic_shipping=cn_domestic_shipping,
            color=color,
            size=size,
            source_url=source_url,
            extra=extra,  # ← dict, без dumps
        )


    async def update(self, *, item_id: int, updates: Dict[str, Any]) -> Optional[int]:
        if not updates:
            return None
        allowed = set(self.REQUIRED_COLUMNS.keys()) - {"id", "created_at"}
        clean: Dict[str, Any] = {}
        for k, v in updates.items():
            if k not in allowed:
                continue
            if k in {"price", "weight_kg", "cn_domestic_shipping"}:
                clean[k] = self._to_numeric(v)
            else:
                clean[k] = v
        if not clean:
            return None

        set_clause = ', '.join(f"{k} = ${i+2}" for i, k in enumerate(clean.keys()))
        row = await self.conn.fetchrow(
            f"UPDATE items SET {set_clause}, updated_at=NOW() WHERE id=$1 RETURNING cargo_id",
            *([item_id] + list(clean.values()))
        )
        return row['cargo_id'] if row else None


    async def delete(self, *, item_id: int) -> Optional[int]:
        row = await self.conn.fetchrow("DELETE FROM items WHERE id=$1 RETURNING cargo_id", item_id)
        return row['cargo_id'] if row else None


    async def get(self, *, item_id: int) -> Optional[dict]:
        row = await self.conn.fetchrow("SELECT * FROM items WHERE id=$1", item_id)
        return dict(row) if row else None


    async def list_by_user(self, *, user_id: int, limit: int = 100, offset: int = 0) -> List[dict]:
        rows = await self.conn.fetch(
            """
            SELECT * FROM items WHERE user_id=$1
            ORDER BY created_at DESC, id DESC
            LIMIT $2 OFFSET $3
            """,
            user_id, limit, offset
        )
        return [dict(r) for r in rows]


    async def list_by_cargo(self, *, cargo_id: int) -> List[dict]:
        rows = await self.conn.fetch("SELECT * FROM items WHERE cargo_id=$1 ORDER BY id", cargo_id)
        return [dict(r) for r in rows]
    
    async def total_spent_by_user(self, *, user_id: int) -> Decimal:
        value = await self.conn.fetchval(
            "SELECT COALESCE(SUM(price * quantity), 0) FROM items WHERE user_id=$1",
            user_id
        )
        return Decimal(str(value or 0))
    
    async def count_by_cargo(self, *, cargo_id: int) -> int:
        return await self.conn.fetchval(
            "SELECT COUNT(*) FROM items WHERE cargo_id=$1",
            cargo_id
        )

    async def list_by_cargo_paginated(self, *, cargo_id: int, limit: int, offset: int) -> list[dict]:
        rows = await self.conn.fetch(
            """
            SELECT * FROM items
            WHERE cargo_id=$1
            ORDER BY id DESC
            LIMIT $2 OFFSET $3
            """,
            cargo_id, limit, offset
        )
        return [dict(r) for r in rows]

    async def count_by_cargo_for_user(self, *, cargo_id: int, user_id: int) -> int:
        return await self.conn.fetchval(
            "SELECT COUNT(*) FROM items WHERE cargo_id=$1 AND user_id=$2",
            cargo_id, user_id
        )

    async def totals_for_user_in_cargo(self, *, cargo_id: int, user_id: int) -> tuple[Decimal, Decimal]:
        """
        Возвращает (goods_usd, weight_kg) по пользователю в указанной посылке.

        Важно: "точная" сумма умножается на пользовательский курс:
            goods_usd = SUM(i.price * i.quantity) * users.rate
        Вес считается как:
            weight_kg = SUM(i.weight_kg * i.quantity)
        """
        row = await self.conn.fetchrow(
            """
            SELECT
                COALESCE(SUM(i.price * i.quantity), 0)
                    * (SELECT COALESCE(u.rate, 1) FROM users u WHERE u.id = $2)
                    AS total_goods_usd,
                COALESCE(SUM(i.weight_kg * i.quantity), 0) AS total_weight_kg
            FROM items i
            WHERE i.cargo_id = $1 AND i.user_id = $2
            """,
            cargo_id, user_id
        )
        return (
            Decimal(str(row["total_goods_usd"])),
            Decimal(str(row["total_weight_kg"])),
        )


    async def users_in_cargo(self, *, cargo_id: int) -> list[int]:
        """
        Список user_id, у кого есть товары в этой посылке.
        Удобно для settlement_by_cargo.
        """
        rows = await self.conn.fetch(
            "SELECT DISTINCT user_id FROM items WHERE cargo_id=$1 ORDER BY user_id",
            cargo_id
        )
        return [r["user_id"] for r in rows]


    async def list_by_cargo_for_user_paginated(
        self, *, cargo_id: int, user_id: int, limit: int, offset: int
    ) -> list[dict]:
        rows = await self.conn.fetch(
            """
            SELECT * FROM items
            WHERE cargo_id=$1 AND user_id=$2
            ORDER BY id DESC
            LIMIT $3 OFFSET $4
            """,
            cargo_id, user_id, limit, offset
        )
        return [dict(r) for r in rows]


    async def list_by_cargo_paginated(self, *, cargo_id: int, limit: int, offset: int) -> list[dict]:
        rows = await self.conn.fetch(
            """
            SELECT * FROM items
            WHERE cargo_id=$1
            ORDER BY id DESC
            LIMIT $2 OFFSET $3
            """,
            cargo_id, limit, offset
        )
        return [dict(r) for r in rows]

    async def list_with_owner_by_cargo(self, *, cargo_id: int) -> list[dict]:
        rows = await self.conn.fetch(
            """
            SELECT i.*,
                   t.name AS item_type_name,
                   u.id   AS user_id,
                   u.name, u.surname, u.phone_number,
                   u.rate AS user_rate
            FROM items i
            LEFT JOIN cargo_types t ON t.id = i.item_type_id
            LEFT JOIN users u ON u.id = i.user_id
            WHERE i.cargo_id=$1
            ORDER BY i.id
            """,
            cargo_id
        )
        return [dict(r) for r in rows]

    async def users_in_cargo(self, *, cargo_id: int) -> List[int]:
        rows = await self.conn.fetch("SELECT DISTINCT user_id FROM items WHERE cargo_id=$1", cargo_id)
        return [int(r['user_id']) for r in rows]
    
    async def sum_cny_for_user_in_cargo(self, *, cargo_id: int, user_id: int) -> Decimal:
        """
        Сумма price * quantity в юанях по конкретному пользователю в указанной посылке.
        """
        value = await self.conn.fetchval(
            """
            SELECT COALESCE(SUM(price * quantity), 0)
            FROM items
            WHERE cargo_id=$1 AND user_id=$2
            """,
            cargo_id, user_id
        )
        return Decimal(str(value or 0))

    def _to_numeric(value) -> Optional[Decimal]:
        if value is None:
            return None
        if isinstance(value, Decimal):
            return value
        try:
            return Decimal(str(value))
        except Exception:
            return None


# --------------------------- Service-layer --------------------------

class CargoService:
    """
    Высокоуровневый сервис. Достаточно передать только conn.
    Имеет init() для создания таблиц.
    """

    def __init__(self, *, conn: asyncpg.Connection):
        self.conn = conn
        self.cargo_types = CargoTypesDB(conn=conn)
        self.cargos = CargosDB(conn=conn)
        self.pay = CargoPaymentsDB(conn=self.conn)
        self.items = ItemsDB(conn=conn)
        self.users = UsersDB(conn=conn)

    async def init(self) -> None:
        # вызови init у всех таблиц, включая платежи
        await self.cargos.init()
        await self.items.init()
        await self.cargo_types.init()
        await self.pay.init()
        # инициализация прочих таблиц как у тебя

    async def _resolve_item_type_id(self, item_type_code: str) -> int:
        item_type_id = await self.cargo_types.get_id_by_code(code=item_type_code)
        if not item_type_id:
            raise ValueError(f"Неизвестный тип товара: {item_type_code}")
        return int(item_type_id)

    async def add_item_to_shared(
        self,
        *,
        user_id: int,
        item_type_code: str,
        title: str,
        photo_file_id: Optional[str],
        price: Any,
        quantity: int,
        color: Optional[str],
        size: Optional[str],
        source_url: Optional[str],
        extra: Optional[Dict[str, Any]] = None,
        weight_kg: Any = 0,
        cn_domestic_shipping: Any = 0,
    ) -> asyncpg.Record:
        item_type_id = await self._resolve_item_type_id(item_type_code)
        cargo = await self.cargos.find_or_create_open_shared(cargo_type_id=item_type_id)
        cargo_id = int(cargo['id'])

        # print(f'{extra} (тип ДО={type(extra)})')
        extra = json.dumps(extra, ensure_ascii=False)
        # print(f'{extra} (тип ПОСЛЕ={type(extra)})')
        item_data = {
            "title": title,
            "price": price,
            "quantity": int(quantity),
            "weight_kg": weight_kg,
            "cn_domestic_shipping": cn_domestic_shipping,
            "color": color,
            "size": size,
            "source_url": source_url,
            "photo_file_id": photo_file_id,
            "extra": extra or {},
        }
        return await self.items.add_from_dict(
            user_id=user_id,
            item_type_id=item_type_id,
            data=item_data,
            cargo_id=cargo_id,
        )

    async def add_item_to_personal(
        self,
        *,
        user_id: int,
        item_type_code: str,
        title: str,
        cargo_id: int,
        confirm_mixed: bool,
        photo_file_id: Optional[str],
        price: Any,
        quantity: int,
        color: Optional[str],
        size: Optional[str],
        source_url: Optional[str],
        extra: Optional[Dict[str, Any]] = None,
        weight_kg: Any = 0,
        cn_domestic_shipping: Any = 0,
    ) -> asyncpg.Record:
        item_type_id = await self._resolve_item_type_id(item_type_code)
        if item_type_code == "mixed" and not confirm_mixed:
            raise ValueError("Для смешанного типа нужно подтверждение (confirm_mixed=True).")

        item_data = {
            "title": title,
            "price": price,
            "quantity": int(quantity),
            "weight_kg": weight_kg,
            "cn_domestic_shipping": cn_domestic_shipping,
            "color": color,
            "size": size,
            "source_url": source_url,
            "photo_file_id": photo_file_id,
            "extra": extra or {},
        }
        return await self.items.add_from_dict(
            user_id=user_id,
            item_type_id=item_type_id,
            data=item_data,
            cargo_id=int(cargo_id),
        )

    async def cargo_items_with_owner(self, *, cargo_id: int) -> list[dict]:
        data = await self.items.list_with_owner_by_cargo(cargo_id=cargo_id)
        # print(data)
        return data

    async def compute_pricing_two_legs(self, *, cargo_id: int) -> dict:
        """
        Плечо 1 (CN→MSK): тариф берём из cargo_types.rate_per_kg_usd по cargo_type_id.
        Плечо 2 (MSK→BY): правило — минимум 10$, +1$/кг за каждый кг после 10 кг.
        Оба плеча считают от округлённого вверх до 0.1 кг веса.
        """
        cargo = await self.cargos.get(cargo_id=cargo_id)
        if not cargo:
            raise ValueError("Груз не найден")

        # гарантируем актуальный вес
        await self.cargos.recalc_weight_and_count(cargo_id=cargo_id)
        cargo = await self.cargos.get(cargo_id=cargo_id)

        total_weight = Decimal(str(cargo.get('total_weight_kg') or 0))
        step = Decimal('0.1')
        chargeable = (total_weight / step).to_integral_value(rounding=ROUND_UP) * step  # кратно 0.1 кг

        # ---- Плечо 1: CN→MSK по тарифу из cargo_types ----
        ct = await self.cargo_types.get(cargo_type_id=cargo['cargo_type_id'])
        r1 = Decimal(str(ct['rate_per_kg_usd'])) if ct and ct.get('rate_per_kg_usd') is not None else Decimal('0')
        cost1 = (chargeable * r1).quantize(Decimal('0.01'), rounding=ROUND_UP)

        # ---- Плечо 2: MSK→BY по правилу 10$ + 1$/кг после 10 кг ----
        base_usd = Decimal('10')
        threshold_kg = Decimal('10.0')
        per_extra_kg_usd = Decimal('1')

        if chargeable <= threshold_kg:
            cost2 = base_usd
            extra_kgs = Decimal('0')
        else:
            # кол-во "лишних" кг округляем вверх до целого (если вес 10.1 → 1 кг)
            extra_kgs = (chargeable - threshold_kg).to_integral_value(rounding=ROUND_UP)
            cost2 = base_usd + extra_kgs * per_extra_kg_usd

        # Итоговая структура (settlement_by_cargo использует только delivery_cost_usd)
        return {
            'total_weight_kg': float(total_weight),
            'chargeable_weight_kg': float(chargeable),
            'cn_to_msk': {
                'rate_per_kg_usd': float(r1),
                'delivery_cost_usd': float(cost1),
            },
            'msk_to_by': {
                # оставляю подробности правила на будущее/для PDF
                'delivery_cost_usd': float(cost2),
                'rule': {
                    'base_usd': float(base_usd),
                    'threshold_kg': float(threshold_kg),
                    'per_extra_kg_usd': float(per_extra_kg_usd),
                    'extra_kgs': float(extra_kgs),
                }
            },
        }
    
    async def settlement_by_cargo(self, *, cargo_id: int) -> dict:
        """
        Сводка по людям (всё в $):
        - товар в $ (через user.rate)
        - доли доставки по двум плечам в $ пропорционально весу
        - оплачено/остатки + авансы/возвраты
        - баланс по доставке и «к возврату», если переплата
        """
        from decimal import Decimal, ROUND_HALF_UP

        cargo = await self.cargos.get(cargo_id=cargo_id)
        if not cargo:
            raise ValueError("Груз не найден")

        legs = await self.compute_pricing_two_legs(cargo_id=cargo_id)
        users = await self.items.users_in_cargo(cargo_id=cargo_id)

        total_weight = Decimal('0')
        weights: dict[int, Decimal] = {}
        goods_usd: dict[int, Decimal] = {}

        for uid in users:
            goods_sum_usd, w = await self.items.totals_for_user_in_cargo(cargo_id=cargo_id, user_id=uid)
            goods_usd[uid] = goods_sum_usd
            weights[uid] = w
            total_weight += w

        if total_weight <= 0:
            total_weight = Decimal('1')

        leg1_total = Decimal(str(legs['cn_to_msk']['delivery_cost_usd']))
        leg2_total = Decimal(str(legs['msk_to_by']['delivery_cost_usd']))

        payments = await CargoPaymentsDB(conn=self.conn).sums_by_cargo_grouped(cargo_id=cargo_id)

        rows: list[dict] = []
        for uid in users:
            goods_usd, weight_kg = await self.items.totals_for_user_in_cargo(cargo_id=cargo_id, user_id=uid)

            total_w = Decimal(str(legs.get("total_weight_kg", 0))) or Decimal("0")
            share = (weight_kg / total_w) if total_w > 0 else Decimal("0")

            msk_total = Decimal(str(legs["cn_to_msk"]["delivery_cost_usd"]))
            by_total  = Decimal(str(legs["msk_to_by"]["delivery_cost_usd"]))
            msk_usd   = (msk_total * share).quantize(Decimal("0.01"), ROUND_HALF_UP)
            by_usd    = (by_total  * share).quantize(Decimal("0.01"), ROUND_HALF_UP)

            # оплатёжки
            pay = payments
            goods_paid_usd = pay.get((uid, "goods_usd"),    Decimal("0")).quantize(Decimal("0.01"))
            msk_paid_usd   = pay.get((uid, "delivery_msk"), Decimal("0")).quantize(Decimal("0.01"))
            by_paid_usd    = pay.get((uid, "delivery_by"),  Decimal("0")).quantize(Decimal("0.01"))
            advance_usd    = pay.get((uid, "advance"),      Decimal("0")).quantize(Decimal("0.01"))
            other_usd      = pay.get((uid, "other"),        Decimal("0")).quantize(Decimal("0.01"))

            # построчные недо-/переплаты
            goods_diff = (goods_paid_usd - goods_usd).quantize(Decimal("0.01"))
            msk_diff   = (msk_paid_usd   - msk_usd).quantize(Decimal("0.01"))
            by_diff    = (by_paid_usd    - by_usd).quantize(Decimal("0.01"))

            # сумма переплат по компонентам (только положительные части)
            components_overpay = sum(x for x in (goods_diff, msk_diff, by_diff) if x > 0)
            # сумма недоплат по компонентам (только отрицательные; как положительное число)
            components_underpay = sum((-x) for x in (goods_diff, msk_diff, by_diff) if x < 0)

            # итого к оплате до учёта авансов/прочего — это недоплаты
            gross_due = components_underpay

            # зачёт авансов/прочего в уменьшение к оплате
            net_due = (gross_due - advance_usd - other_usd).quantize(Decimal("0.01"))
            if net_due < 0:
                # аванс перекрыл всё — образовалась переплата
                refund_after_advance = (-net_due)
                net_due = Decimal("0.00")
            else:
                refund_after_advance = Decimal("0.00")

            # итоговая переплата = переплата по компонентам + переплата от авансов
            total_overpay = (components_overpay + refund_after_advance).quantize(Decimal("0.01"))

            rows.append({
                "user_id": uid,
                "weight_kg":          weight_kg.quantize(Decimal("0.001")),
                "goods_usd":          goods_usd.quantize(Decimal("0.01")),
                "goods_paid_usd":     goods_paid_usd,
                "msk_usd":            msk_usd,          "msk_paid_usd": msk_paid_usd,
                "by_usd":             by_usd,           "by_paid_usd":  by_paid_usd,
                "advance_usd":        advance_usd,
                "total_due_usd":      net_due,          # к оплате
                "total_overpay_usd":  total_overpay,    # сумма всех переплат (по строкам + от авансов)
                # для покомпонентного вывода:
                "goods_diff":         goods_diff,
                "msk_diff":           msk_diff,
                "by_diff":            by_diff,
            })

        return {"cargo": cargo, "legs": legs, "users": rows}


    async def get_cargo_info(
        self,
        *,
        cargo_id: int,
        for_user_id: int | None = None,   # если нужен блок по конкретному юзеру
    ) -> dict | None:
        """
        Возвращает агрегированную инфу по посылке:
        - cargo, cargo_type_name
        - pricing (две ноги)
        - items (с данными владельца), items_count
        - users_in, users_count
        - суммы по всем товарам (CNY, USD по курсам юзеров, USD по CLEAR_RATE, profit)
        - (опционально) блок по конкретному пользователю: сумма в CNY и USD по его курсу
        """
        from decimal import Decimal

        # --- сама посылка ---
        cargo = await self.cargos.get(cargo_id=cargo_id)
        if not cargo:
            return None

        # имя типа
        cargo_type_name = await self.cargo_types.get_name_by_id(
            cargo_type_id=cargo["cargo_type_id"]
        )

        # расчёт двух плеч
        pricing = await self.compute_pricing_two_legs(cargo_id=cargo_id)

        # товары с данными владельца (list_with_owner_by_cargo)
        items = await self.items.list_with_owner_by_cargo(cargo_id=cargo_id)
        items_count = len(items)

        # пользователи в посылке
        users_in = await self.items.users_in_cargo(cargo_id=cargo_id)
        users_count = len(users_in)

        # --- общая сумма в CNY по всем товарам ---
        sum_cny = Decimal("0")

        # одновременно посчитаем price_usd по каждому товару (для экспорта)
        for it in items:
            price = Decimal(str(it.get("price") or 0))
            qty   = Decimal(str(it.get("quantity") or 1))
            row_sum_cny = price * qty
            sum_cny += row_sum_cny

            # курс юзера для этой позиции (если есть)
            rate = it.get("user_rate")
            if rate is None:
                it["price_usd"] = None
            else:
                try:
                    rate_dec = Decimal(str(rate))
                    it["price_usd"] = (row_sum_cny * rate_dec).quantize(Decimal("0.01"))
                except Exception:
                    it["price_usd"] = None

        # --- сумма в USD по курсу каждого юзера (агрегатно) ---
        sum_usd_by_user = Decimal("0")
        per_user_totals: dict[int, dict] = {}

        for uid in users_in:
            goods_usd, _ = await self.items.totals_for_user_in_cargo(
                cargo_id=cargo_id,
                user_id=uid,
            )
            goods_usd = Decimal(str(goods_usd))
            sum_usd_by_user += goods_usd
            per_user_totals[uid] = {"goods_usd": goods_usd}

        sum_usd_by_user = sum_usd_by_user.quantize(Decimal("0.01"))

        # --- «честная» сумма в USD по CLEAR_RATE ---
        clear_rate = Decimal(str(CLEAR_RATE))
        sum_usd_clear = (sum_cny * clear_rate).quantize(Decimal("0.01"))

        # --- прибыль ---
        profit = (sum_usd_by_user - sum_usd_clear).quantize(Decimal("0.01"))

        result: dict[str, object] = {
            "cargo": cargo,
            "cargo_type_name": cargo_type_name,
            "pricing": pricing,
            "items": items,              # ← товары уже с owner-данными и price_usd
            "items_count": items_count,
            "users_in": users_in,
            "users_count": users_count,
            "sum_cny": sum_cny,
            "sum_usd_by_user": sum_usd_by_user,
            "sum_usd_clear": sum_usd_clear,
            "profit": profit,
            "per_user_totals": per_user_totals,
        }

        # --- блок по конкретному пользователю (для профиля) ---
        if for_user_id is not None:
            user = await self.users.get_user(for_user_id)
            rate = Decimal(str((user or {}).get("rate") or DEFAULT_RATE))

            user_items = [it for it in items if it.get("user_id") == for_user_id]
            user_items_count = len(user_items)

            # агрегат из БД + fallback по item-ам
            try:
                sum_cny_user = await self.items.sum_cny_for_user_in_cargo(
                    cargo_id=cargo_id,
                    user_id=for_user_id,
                )
                sum_cny_user = Decimal(str(sum_cny_user))
            except Exception:
                sum_cny_user = Decimal("0")
                for it in items:
                    if it.get("user_id") != for_user_id:
                        continue
                    price = Decimal(str(it.get("price") or 0))
                    qty   = Decimal(str(it.get("quantity") or 1))
                    sum_cny_user += price * qty

            sum_usd_user = (sum_cny_user * rate).quantize(Decimal("0.01"))

            result["current_user"] = {
                "row": user,
                "id": for_user_id,
                "rate": rate,
                "sum_cny": sum_cny_user,
                "sum_usd": sum_usd_user,
                "items_count": user_items_count,
            }

        return result
    
    async def get_cargo_export_payload(
        self,
        *,
        cargo_id: int,
    ) -> dict | None:
        """
        Упрощённый payload именно для экспорта товаров:
        - cargo (дополнительно прокидываем cargo_type_name)
        - items (с owner-данными и price_usd)
        """
        info = await self.get_cargo_info(cargo_id=cargo_id)
        if not info:
            return None

        cargo = dict(info["cargo"])
        cargo["type_name"] = info.get("cargo_type_name")

        return {
            "cargo": cargo,
            "items": info["items"],
        }

    async def get_item_detailed_info(
        self,
        *,
        cargo_id: int,
        item_id: int,
    ) -> dict | None:
        """
        Детальная информация по одному товару в посылке:
        - cargo, item, legs (две доставки)
        - цена товара (CNY -> USD, за 1 шт и за все)
        - доставка (CN→MSK и MSK→BY) пропорционально весу этого товара
        - итоговая цена за 1 шт и за все шт
        """
        from decimal import Decimal, ROUND_HALF_UP

        # --- груз и товар ---
        cargo = await self.cargos.get(cargo_id=cargo_id)
        if not cargo:
            return None

        item = await self.items.get(item_id=item_id)
        if not item or int(item.get("cargo_id") or 0) != int(cargo_id):
            return None

        # --- тарифы по двум плечам ---
        legs = await self.compute_pricing_two_legs(cargo_id=cargo_id)

        # --- базовые числа по товару ---
        price_cny = Decimal(str(item.get("price") or 0))
        qty       = Decimal(str(item.get("quantity") or 1))
        weight_kg_single = Decimal(str(item.get("weight_kg") or 0))
        weight_kg_total  = (weight_kg_single * qty).quantize(Decimal("0.001"))

        # курс берём из владельца товара
        owner = await self.users.get_user(item["user_id"])
        rate  = Decimal(str((owner or {}).get("rate") or DEFAULT_RATE))

        # --- цена товара в USD ---
        price_usd_per_unit = (price_cny * rate).quantize(Decimal("0.01"), ROUND_HALF_UP)
        price_usd_total    = (price_usd_per_unit * qty).quantize(Decimal("0.01"), ROUND_HALF_UP)

        # --- доля доставки по весу ---
        total_weight_all = Decimal(str(legs.get("total_weight_kg") or 0))
        if total_weight_all > 0:
            share = (weight_kg_total / total_weight_all)
        else:
            share = Decimal("0")

        # --- доставка по двум плечам для ЭТОГО товара (за все шт сразу) ---
        cn_msk_total_usd = Decimal(str(legs["cn_to_msk"]["delivery_cost_usd"]))
        msk_by_total_usd = Decimal(str(legs["msk_to_by"]["delivery_cost_usd"]))

        delivery_cn_msk = (cn_msk_total_usd * share).quantize(Decimal("0.01"), ROUND_HALF_UP)
        delivery_msk_by = (msk_by_total_usd * share).quantize(Decimal("0.01"), ROUND_HALF_UP)
        delivery_total  = (delivery_cn_msk + delivery_msk_by).quantize(Decimal("0.01"), ROUND_HALF_UP)

        # доставка «за 1 шт» (если qty > 0)
        if qty > 0:
            delivery_per_unit = (delivery_total / qty).quantize(Decimal("0.01"), ROUND_HALF_UP)
        else:
            delivery_per_unit = delivery_total

        # --- итоговая цена ---
        final_per_unit = (price_usd_per_unit + delivery_per_unit).quantize(Decimal("0.01"), ROUND_HALF_UP)
        final_total = (final_per_unit * qty).quantize(Decimal("0.01"), ROUND_HALF_UP)

        return {
            "cargo": cargo,
            "item": item,
            "legs": legs,

            "price_cny_per_unit": price_cny,
            "price_usd_per_unit": price_usd_per_unit,
            "price_usd_total":  price_usd_total,
            "rate": rate,
            "quantity": qty,

            "weight_kg_single": weight_kg_single,
            "weight_kg_total": weight_kg_total,

            "delivery_cn_msk_usd": delivery_cn_msk,
            "delivery_msk_by_usd": delivery_msk_by,
            "delivery_total_usd": delivery_total,
            "delivery_per_unit_usd": delivery_per_unit,

            "final_per_unit_usd": final_per_unit,
            "final_total_usd": final_total,
        }

    async def get_admin_items_export_payload(
        self,
        *,
        cargo_id: int,
    ) -> dict | None:
        """
        Готовый payload для админского PDF по товарам посылки.

        Возвращает:
        {
          "cargo": {...},
          "items": [  # каждый товар уже с готовыми денежными полями
             {
               ... исходные поля items + owner ...,
               "goods_usd_per_unit": Decimal,
               "delivery_per_unit_usd": Decimal,
               "final_total_usd": Decimal,
             },
             ...
          ]
        }

        Вся математика тут, PDF только подставляет.
        """
        from decimal import Decimal, ROUND_HALF_UP

        cargo = await self.cargos.get(cargo_id=cargo_id)
        if not cargo:
            return None

        # тарифы и общая доставка по двум плечам
        legs = await self.compute_pricing_two_legs(cargo_id=cargo_id)

        # все товары + владелец + user_rate
        items = await self.items.list_with_owner_by_cargo(cargo_id=cargo_id)

        # общий вес по посылке (берём из legs, где он уже пересчитан)
        total_weight_all = Decimal(str(legs.get("total_weight_kg") or 0))
        if total_weight_all <= 0:
            # запасной вариант: считаем из товаров
            total_weight_all = Decimal("0")
            for it in items:
                qty = Decimal(str(it.get("quantity") or 1))
                w_single = Decimal(str(it.get("weight_kg") or 0))
                total_weight_all += (w_single * qty)
            if total_weight_all <= 0:
                total_weight_all = Decimal("1")

        cn_msk_total_usd = Decimal(str(legs["cn_to_msk"]["delivery_cost_usd"]))
        msk_by_total_usd = Decimal(str(legs["msk_to_by"]["delivery_cost_usd"]))
        delivery_total_all = cn_msk_total_usd + msk_by_total_usd

        enriched: list[dict] = []

        for it in items:
            it = dict(it)  # на всякий случай делаем копию

            price_cny = Decimal(str(it.get("price") or 0))
            qty       = Decimal(str(it.get("quantity") or 1))
            w_single  = Decimal(str(it.get("weight_kg") or 0))
            w_total   = (w_single * qty).quantize(Decimal("0.001"))

            rate = Decimal(str(it.get("user_rate") or DEFAULT_RATE))

            # цена товара в USD
            goods_usd_per_unit = (price_cny * rate).quantize(Decimal("0.01"), ROUND_HALF_UP)
            goods_usd_total    = (goods_usd_per_unit * qty).quantize(Decimal("0.01"), ROUND_HALF_UP)

            # доля доставки по весу
            share = (w_total / total_weight_all) if total_weight_all > 0 else Decimal("0")

            delivery_total_item = (delivery_total_all * share).quantize(Decimal("0.01"), ROUND_HALF_UP)
            if qty > 0:
                delivery_per_unit = (delivery_total_item / qty).quantize(Decimal("0.01"), ROUND_HALF_UP)
            else:
                delivery_per_unit = delivery_total_item

            # итог
            final_per_unit = (goods_usd_per_unit + delivery_per_unit).quantize(Decimal("0.01"), ROUND_HALF_UP)
            final_total    = (final_per_unit * qty).quantize(Decimal("0.01"), ROUND_HALF_UP)

            it["goods_usd_per_unit"]    = goods_usd_per_unit
            it["goods_usd_total"]       = goods_usd_total
            it["delivery_per_unit_usd"] = delivery_per_unit
            it["delivery_total_usd"]    = delivery_total_item
            it["final_per_unit_usd"]    = final_per_unit
            it["final_total_usd"]       = final_total

            enriched.append(it)

        cargo_out = dict(cargo)
        cargo_out["items_count"] = len(enriched)

        return {
            "cargo": cargo_out,
            "items": enriched,
        }

    
# ---------------------------------------------------------


class CargoPaymentsDB:
    """Учёт платежей по посылке/пользователю."""
    REQUIRED_COLUMNS = {
        'id': 'BIGSERIAL PRIMARY KEY',
        'cargo_id': 'BIGINT NOT NULL',
        'user_id': 'BIGINT NOT NULL',
        'kind': "TEXT NOT NULL",            # 'goods_cny'|'delivery_msk'|'delivery_by'|'advance'|'refund'|'other'
        'amount_usd': "NUMERIC(12,2)",
        'amount_cny': "NUMERIC(12,2)",
        'note': "TEXT",
        'created_at': 'TIMESTAMP DEFAULT NOW()'
    }

    def __init__(self, *, conn: asyncpg.Connection):
        self.conn = conn

    async def init(self) -> None:
        cols = ', '.join(f"{c} {t}" for c, t in self.REQUIRED_COLUMNS.items())
        await self.conn.execute(f"CREATE TABLE IF NOT EXISTS cargo_payments ({cols})")

    async def add(
        self,
        *,
        cargo_id: int,
        user_id: int,
        kind: str,
        amount_usd: Optional[Decimal] = None,
        amount_cny: Optional[Decimal] = None,
        note: Optional[str] = None
    ) -> dict:
        row = await self.conn.fetchrow(
            """
            INSERT INTO cargo_payments(cargo_id, user_id, kind, amount_usd, amount_cny, note)
            VALUES ($1,$2,$3,$4,$5,$6) RETURNING *
            """,
            cargo_id, user_id, kind, amount_usd, amount_cny, note
        )
        return dict(row)

    async def sums_by_cargo_grouped(self, *, cargo_id: int) -> dict[tuple[int, str], Decimal]:
        """
        Возвращает словарь {(user_id, kind): amount_usd} по посылке.
        Все платежи ведём в USD, kinds: goods_usd, delivery_msk, delivery_by, advance, refund, other.
        """
        rows = await self.conn.fetch(
            """
            SELECT user_id, kind, COALESCE(SUM(amount_usd), 0) AS amount_usd
            FROM cargo_payments
            WHERE cargo_id = $1
            GROUP BY user_id, kind
            """,
            cargo_id
        )
        from decimal import Decimal
        out: dict[tuple[int, str], Decimal] = {}
        for r in rows:
            out[(r["user_id"], r["kind"])] = Decimal(str(r["amount_usd"]))
        return out