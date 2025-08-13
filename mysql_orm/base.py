import aiomysql
import re
import asyncio
import atexit
from contextlib import asynccontextmanager
from .fields import Field, ForeignKey


class ModelMeta(type):
    def __new__(cls, name, bases, attrs):
        fields = {k: v for k, v in attrs.items() if isinstance(v, Field)}
        meta = attrs.get('Meta', None)
        snake = cls.camel_to_snake(name)
        table = getattr(meta, 'table', f"{snake}s")
        attrs['__fields__'] = fields
        attrs['__table__'] = table
        return super().__new__(cls, name, bases, attrs)

    @staticmethod
    def camel_to_snake(name: str) -> str:
        s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
        return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()


class DB:
    _config = None
    _pool = None
    _auto_close_enabled = False

    @classmethod
    def connect(cls, autoclose: bool = True, **kwargs):
        """Store DB config and autoclose option."""
        # сохраняем настройку автозакрытия отдельно
        cls._config = dict(kwargs)
        cls._config['autocommit'] = kwargs.get('autocommit', False)
        cls._config['autoclose'] = autoclose

        # включаем авто-закрытие пула при завершении процесса
        if autoclose:
            cls._enable_auto_close()

    @classmethod
    def _enable_auto_close(cls):
        if cls._auto_close_enabled:
            return
        cls._auto_close_enabled = True

        def _shutdown():
            # на выходе из процесса аккуратно закрываем пул
            try:
                asyncio.run(cls.close())
            except RuntimeError:
                # если луп уже в странном состоянии — молча пропускаем
                pass

        atexit.register(_shutdown)

    @classmethod
    def is_autocommit(cls) -> bool:
        return bool(cls._config and cls._config.get("autocommit", False))

    @classmethod
    def is_autoclose(cls) -> bool:
        return bool(cls._config and cls._config.get("autoclose", True))

    @classmethod
    async def _create_pool(cls):
        if not cls._config:
            raise ConnectionError("Call `DB.connect(...)` first.")

        # ВАЖНО: не передавать 'autoclose' в aiomysql
        cfg = dict(cls._config)
        cfg.pop("autoclose", None)

        try:
            cls._pool = await aiomysql.create_pool(**cfg, minsize=1, maxsize=10)
        except Exception as e:
            # авто-создание БД, если она отсутствует
            if 'Unknown database' in str(e):
                db_name = cls._config.get("db")
                print(f"[info] Database '{db_name}' not found, creating it...")

                temp_cfg = dict(cfg)
                temp_cfg.pop("db", None)

                tmp_pool = await aiomysql.create_pool(**temp_cfg, minsize=1, maxsize=1)
                async with tmp_pool.acquire() as tmp_conn:
                    async with tmp_conn.cursor() as cur:
                        await cur.execute(f"CREATE DATABASE IF NOT EXISTS `{db_name}`")
                        await tmp_conn.commit()
                tmp_pool.close()
                await tmp_pool.wait_closed()

                cls._pool = await aiomysql.create_pool(**cfg, minsize=1, maxsize=10)
            else:
                raise ConnectionError(f"Failed to create pool: {e}")

    @classmethod
    async def pool(cls):
        if cls._pool is None:
            await cls._create_pool()
        return cls._pool

    @classmethod
    async def conn(cls):
        pool = await cls.pool()
        return await pool.acquire()

    @classmethod
    async def release(cls, conn):
        # ВСЕГДА релизим соединение обратно в пул
        pool = await cls.pool()
        pool.release(conn)

    @classmethod
    async def close(cls):
        # Закрываем пул и ждём, пока все коннекты закроются
        if cls._pool is not None:
            cls._pool.close()
            await cls._pool.wait_closed()
            cls._pool = None

    # Дополнительно: удобные контексты (необязательно, но полезно)
    @classmethod
    @asynccontextmanager
    async def session(cls):
        """Reuse a single connection for multiple operations (no explicit transaction)."""
        conn = await cls.conn()
        try:
            yield conn
        finally:
            await cls.release(conn)

    @classmethod
    @asynccontextmanager
    async def transaction(cls):
        """
        ACID transaction:
          START TRANSACTION -> yield -> COMMIT / ROLLBACK
        Работает независимо от глобального autocommit.
        """
        conn = await cls.conn()
        try:
            async with conn.cursor() as cur:
                await cur.execute("START TRANSACTION")
            try:
                yield conn
            except Exception:
                await conn.rollback()
                raise
            else:
                await conn.commit()
        finally:
            await cls.release(conn)


_SENTINEL = object()


class BaseModel(metaclass=ModelMeta):
    def __init__(self, **kwargs):
        for field in self.__fields__:
            setattr(self, field, kwargs.get(field))

    def to_dict(self):
        return {k: getattr(self, k) for k in self.__fields__}

    def __repr__(self):
        return f"<{self.__class__.__name__} {self.to_dict()}>"

    @staticmethod
    def quote(name: str) -> str:
        return f"`{name}`"

    @classmethod
    def _ensure_column(cls, col: str) -> str:
        if col not in cls.__fields__:
            raise ValueError(f"Unknown column: {col}")
        return col

    @classmethod
    def _build_where_and_params(cls, **kwargs):
        conditions = []
        params = []
        for key, value in kwargs.items():
            if key in ("_db", "_conn"):
                continue
            if "__" in key:
                col, op = key.split("__", 1)
                cls._ensure_column(col)
                if op == "gte":
                    conditions.append(f"{cls.quote(col)} >= %s")
                    params.append(value)
                elif op == "lte":
                    conditions.append(f"{cls.quote(col)} <= %s")
                    params.append(value)
                elif op == "like":
                    conditions.append(f"{cls.quote(col)} LIKE %s")
                    params.append(value)
                elif op == "in":
                    if not value:
                        conditions.append("1=0")
                    else:
                        placeholders = ", ".join(["%s"] * len(value))
                        conditions.append(f"{cls.quote(col)} IN ({placeholders})")
                        params.extend(value)
                else:
                    raise ValueError(f"Unsupported filter operator: {op}")
            else:
                cls._ensure_column(key)
                conditions.append(f"{cls.quote(key)} = %s")
                params.append(value)
        where_sql = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        return where_sql, params

    @classmethod
    async def connect(cls):
        return await DB.conn()
    
    # ------------------------
    # CRUD
    # ------------------------
    @classmethod
    async def create(cls, _conn=None, **kwargs):
        """
        Insert a new row with the provided field values and return an instance.

        Args:
            _conn (aiomysql.Connection|None): optional external connection (e.g., from DB.transaction())

        Returns:
            cls: newly created instance (id is set if declared)

        Example:
        ```
        user = await User.create(name="Alice", email="alice@example.com")

        # inside a transaction:
        async with DB.transaction() as conn:
            u = await User.create(name="X", email="x@x.com", _conn=conn)
        ```
        """
        kwargs.pop("_db", None)
        keys = list(kwargs.keys())
        values = tuple(kwargs[k] for k in keys)

        fields = ", ".join(cls.quote(k) for k in keys)
        placeholders = ", ".join(["%s"] * len(keys))
        sql = f"INSERT INTO {cls.quote(cls.__table__)} ({fields}) VALUES ({placeholders})"

        created_locally = _conn is None
        conn = _conn or await cls.connect()
        try:
            async with conn.cursor() as cur:
                await cur.execute(sql, values)
                if created_locally and not DB.is_autocommit():
                    await conn.commit()
                last_id = cur.lastrowid
        finally:
            if created_locally:
                await DB.release(conn)

        obj = cls(**kwargs)
        if "id" in cls.__fields__:
            setattr(obj, "id", last_id)
        return obj

    @classmethod
    async def all(cls, limit=None, offset=None, order_by=None, _conn=None, **kwargs):
        """
        Fetch all rows (optionally limited and ordered) and return a list of model instances.

        Args:
            limit (int|None): Optional LIMIT clause.
            offset (int|None): Optional OFFSET clause (used with LIMIT).
            order_by (str|None): Column name to order by.
                - Prefix with "-" for DESC (descending order)
                - Without prefix means ASC (ascending order)
            _conn (aiomysql.Connection|None): optional external connection

        Examples:
            ### All users ordered by name ascending (A → Z)
            ```
            users = await User.all(order_by="name")
            ```
            ### Last 5 users by id descending (highest id first)
            ```
            users = await User.all(limit=5, order_by="-id")
            ```

            ### All posts ordered by creation date ascending (oldest first)
            ```
            posts = await Post.all(order_by="created_at")
            ```

            ### All posts ordered by creation date descending (newest first)
            ```
            posts = await Post.all(order_by="-created_at")
            ```
        """
        kwargs.pop("_db", None)
        sql = f"SELECT * FROM {cls.quote(cls.__table__)}"

        if order_by:
            desc = order_by.startswith("-")
            col = order_by[1:] if desc else order_by
            cls._ensure_column(col)
            sql += f" ORDER BY {cls.quote(col)} {'DESC' if desc else 'ASC'}"

        if limit is not None:
            sql += f" LIMIT {int(limit)}"
            if offset is not None:
                sql += f" OFFSET {int(offset)}"

        created_locally = _conn is None
        conn = _conn or await cls.connect()
        try:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(sql)
                rows = await cur.fetchall()
        finally:
            if created_locally:
                await DB.release(conn)
        return [cls(**row) for row in rows]

    @classmethod
    async def filter(cls, limit=None, offset=None, order_by=None, _conn=None, **kwargs):
        """
        Fetch rows matching equality conditions and return a list of model instances.

        Supports extended operators in kwargs:
            - __gte, __lte, __like, __in

        Args:
            limit (int|None): Optional LIMIT clause.
            offset (int|None): Optional OFFSET clause (used with LIMIT).
            order_by (str|None): Column name to order by.
                - Prefix with "-" for DESC (descending order)
                - Without prefix means ASC (ascending order)
            _conn (aiomysql.Connection|None): optional external connection
            **kwargs: Column=value pairs for WHERE conditions (with optional operators).
        """
        where_sql, params = cls._build_where_and_params(**kwargs)
        sql = f"SELECT * FROM {cls.quote(cls.__table__)}{where_sql}"

        if order_by:
            desc = order_by.startswith("-")
            col = order_by[1:] if desc else order_by
            cls._ensure_column(col)
            sql += f" ORDER BY {cls.quote(col)} {'DESC' if desc else 'ASC'}"

        if limit is not None:
            sql += f" LIMIT {int(limit)}"
            if offset is not None:
                sql += f" OFFSET {int(offset)}"

        created_locally = _conn is None
        conn = _conn or await cls.connect()
        try:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(sql, tuple(params))
                rows = await cur.fetchall()
        finally:
            if created_locally:
                await DB.release(conn)
        return [cls(**row) for row in rows]

    @classmethod
    async def get(cls, *, default=_SENTINEL, raise_multiple=True, order_by=None, _conn=None, **kwargs):
        """
        Return exactly one row matching the conditions.

        Behavior:
            - If no rows:
                - raise LookupError (default)
                - OR return `default` if provided (e.g., None)
            - If multiple rows:
                - raise LookupError (default)
                - OR return the first row when `raise_multiple=False`
                  (optionally choose which is "first" via `order_by`)
        """
        if raise_multiple:
            rows = await cls.filter(limit=2, _conn=_conn, **kwargs)
            if not rows:
                if default is _SENTINEL:
                    raise LookupError(f"{cls.__name__}.get() no rows for {kwargs}")
                return default
            if len(rows) > 1:
                raise LookupError(f"{cls.__name__}.get() multiple rows for {kwargs}")
            return rows[0]
        else:
            rows = await cls.filter(limit=1, order_by=order_by, _conn=_conn, **kwargs)
            if not rows:
                if default is _SENTINEL:
                    raise LookupError(f"{cls.__name__}.get() no rows for {kwargs}")
                return default
            return rows[0]

    @classmethod
    async def get_or_create(cls, _conn=None, **kwargs):
        """
        Try to fetch by exact match; if nothing found, create a new row.

        Args:
            _conn (aiomysql.Connection|None): optional external connection

        Returns:
            (cls, bool): (instance, created_flag)
        """
        kwargs.pop("_db", None)
        found = await cls.filter(_conn=_conn, **kwargs)
        if found:
            return found[0], False
        created = await cls.create(_conn=_conn, **kwargs)
        return created, True

    @classmethod
    async def update(cls, filters: dict, updates: dict, _conn=None, **kwargs):
        """
        Update rows that match `filters` with values from `updates`.
        """
        kwargs.pop("_db", None)

        where_sql, where_params = cls._build_where_and_params(**filters)

        if not updates:
            return
        for k in updates.keys():
            cls._ensure_column(k)
        set_clause = ", ".join([f"{cls.quote(k)} = %s" for k in updates])
        params = list(updates.values()) + list(where_params)

        sql = f"UPDATE {cls.quote(cls.__table__)} SET {set_clause}{where_sql}"

        created_locally = _conn is None
        conn = _conn or await cls.connect()
        try:
            async with conn.cursor() as cur:
                await cur.execute(sql, tuple(params))
                if created_locally and not DB.is_autocommit():
                    await conn.commit()
        finally:
            if created_locally:
                await DB.release(conn)

    @classmethod
    async def delete(cls, _conn=None, **kwargs):
        """
        Delete rows matching equality conditions.
        """
        kwargs.pop("_db", None)
        where_sql, params = cls._build_where_and_params(**kwargs)
        if not where_sql:
            # Safety: avoid accidental full-table delete
            raise ValueError("DELETE requires at least one condition")

        sql = f"DELETE FROM {cls.quote(cls.__table__)}{where_sql}"

        created_locally = _conn is None
        conn = _conn or await cls.connect()
        try:
            async with conn.cursor() as cur:
                await cur.execute(sql, tuple(params))
                if created_locally and not DB.is_autocommit():
                    await conn.commit()
        finally:
            if created_locally:
                await DB.release(conn)

    @classmethod
    async def count(cls, _conn=None, **kwargs):
        """
        Return count of matching rows.
        """
        where_sql, params = cls._build_where_and_params(**kwargs)
        sql = f"SELECT COUNT(*) as cnt FROM {cls.quote(cls.__table__)}{where_sql}"

        created_locally = _conn is None
        conn = _conn or await cls.connect()
        try:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(sql, tuple(params))
                row = await cur.fetchone()
        finally:
            if created_locally:
                await DB.release(conn)
        return row["cnt"]

    @classmethod
    async def exists(cls, _conn=None, **kwargs):
        """
        Return True if at least one matching row exists.
        """
        return (await cls.count(_conn=_conn, **kwargs)) > 0

    @classmethod
    def generate_create_table(cls):
        """
        Generate a CREATE TABLE DDL statement based on declared fields.
        Handles ForeignKey references and remembers dependencies.
        """
        columns = []
        foreign_keys = []

        for name, field in cls.__fields__.items():
            if isinstance(field, ForeignKey):
                columns.append(field.ddl(name))
                foreign_keys.append(
                    f"FOREIGN KEY ({cls.quote(name)}) REFERENCES "
                    f"{cls.quote(field.to_model.__table__)}({cls.quote(field.to_field)})"
                )
                cls.__dependencies__ = getattr(cls, '__dependencies__', set())
                cls.__dependencies__.add(field.to_model.__table__)
            else:
                columns.append(field.ddl(name))

        all_defs = columns + foreign_keys
        return (
            f"CREATE TABLE IF NOT EXISTS {cls.quote(cls.__table__)} (\n  "
            + ",\n  ".join(all_defs)
            + "\n);"
        )
