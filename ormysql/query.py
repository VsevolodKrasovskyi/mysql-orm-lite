import aiomysql
import logging
from .db import DB
from .fields import ForeignKey

logging.basicConfig(level=logging.ERROR)
log = logging.getLogger("ORM")

_SENTINEL = object()


class QueryMixin:

    @classmethod
    def _select_fields(cls):
        fields_sql = []
        for name, field in cls.__fields__.items():
            table_name = field.model.__table__
            fields_sql.append(
                f"{cls.quote(table_name)}.{cls.quote(name)} AS {cls.quote(table_name + '__' + name)}"
            )
        return ", ".join(fields_sql)
    
    @classmethod
    def _map_row(cls, row: dict):
        clean = {}
        for key, val in row.items():
            if "__" in key:
                _, col = key.split("__", 1)
                clean[col] = val
            else:
                clean[key] = val
        return clean
    

    @classmethod
    async def create(cls, _conn=None, defaults=None, **kwargs):
        """
        Create a new record in the database.

        Args:
            _conn: Optional existing DB connection.
            **kwargs: Field values to insert.

        Returns:
            Instance of the model with inserted values.

        Example:
            ```python
            user = await User.create(name="John", email="john@example.com")
            ```
        """
        if defaults:
            for k, v in defaults.items():
                kwargs.setdefault(k, v)

        kwargs.pop("_db", None)

        keys = list(kwargs.keys())
        values = tuple(kwargs[k] for k in keys)
        fields = ", ".join(cls.quote(k) for k in keys)
        placeholders = ", ".join(["%s"] * len(keys))
        sql = f"INSERT INTO {cls.quote(cls.__table__)} ({fields}) VALUES ({placeholders})"

        created_locally = _conn is None
        conn = _conn or await cls.connect()
        try:
            log.debug(f"SQL: {sql} VALUES: {values}")
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
        Retrieve all records, optionally with limit, offset, and ordering.

        Args:
            limit (int): Max number of records.
            offset (int): Skip this many records.
            order_by (str): Column name, prefix with '-' for DESC order.
            _conn: Optional DB connection.

        Returns:
            List of model instances.

        Example:
            ```python
            users = await User.all(order_by="-id", limit=10) #DESC
            users = await User.all(order_by="id", limit=10) #ASC
            ```
        """
        sql = f"SELECT {cls._select_fields()} FROM {cls.quote(cls.__table__)}{cls._build_join_clause()}"
        if order_by:
            desc = order_by.startswith("-")
            col = order_by[1:] if desc else order_by
            cls._ensure_column(col)
            table_name = cls.__fields__[col].model.__table__ if getattr(cls, "__joins__", []) else cls.__table__
            sql += f" ORDER BY {cls.quote(table_name)}.{cls.quote(col)} {'DESC' if desc else 'ASC'}"
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
        return [cls(**cls._map_row(row)) for row in rows]

    @classmethod
    async def filter(cls, limit=None, offset=None, order_by=None, _conn=None, **kwargs):
        """
        Retrieve filtered records.

        Args:
            limit (int): Max number of records.
            offset (int): Skip this many records.
            order_by (str): Column name, prefix with '-' for DESC order.
            _conn: Optional DB connection.
            **kwargs: Filter conditions (supports __gte, __lte, __like, __in).

        Returns:
            List of model instances.

        Example:
            ```python
            active_users = await User.filter(is_active=1, age__gte=18)
            active_users = await User.filter(is_active=1, name__like="John%")
            ```
        """
        where_sql, params = cls._build_where_and_params(**kwargs)
        sql = f"SELECT {cls._select_fields()} FROM {cls.quote(cls.__table__)}{cls._build_join_clause()}{where_sql}"
        if order_by:
            desc = order_by.startswith("-")
            col = order_by[1:] if desc else order_by
            cls._ensure_column(col)
            table_name = cls.__fields__[col].model.__table__ if getattr(cls, "__joins__", []) else cls.__table__
            sql += f" ORDER BY {cls.quote(table_name)}.{cls.quote(col)} {'DESC' if desc else 'ASC'}"
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
        return [cls(**cls._map_row(row)) for row in rows]

    @classmethod
    async def get(cls, *, default=None, raise_multiple=False, order_by=None, _conn=None, **kwargs):
        """
        Retrieve a single record.

        Args:
            default: Value to return if no record is found.
            raise_multiple (bool): If True, raise if multiple rows match.
            order_by (str): Column name for ordering.
            _conn: Optional DB connection.
            **kwargs: Filter conditions.

        Returns:
            Single model instance or `default`.

        Example:
            ```python
            user = await User.get(id=1)
            ```
        """
        rows = await cls.filter(limit=1, order_by=order_by, _conn=_conn, **kwargs)
        return rows[0] if rows else default
    
    # Удалить
    @classmethod
    async def get_or_none(cls, _conn=None, **kwargs):
        """
        Retrieve a single record or return None if not found.

        Args:
            _conn: Optional DB connection.
            **kwargs: Filter conditions.

        Returns:
            Model instance or None.

        Behavior:
            - If exactly one row matches, returns it.
            - If no rows match, returns None.
            - If more than one row matches, raises LookupError to prevent ambiguous fetches.

        Example:
            ```python
            user = await User.get_or_none(email="john@example.com")
            if user is None:
                # handle not found
                ...
            ```
        """
        return await cls.get(default=None, raise_multiple=True, _conn=_conn, **kwargs)
    # удалить
    @classmethod
    async def first_or_none(cls, order_by=None, _conn=None, **kwargs):
        """
        Return the first matching record or None.

        Args:
            order_by (str, optional): Column name to order by; prefix with '-' for DESC.
            _conn: Optional DB connection.
            **kwargs: Filter conditions.

        Returns:
            Model instance or None.

        Notes:
            Unlike `get_or_none`, this method never raises due to multiple matches;
            it simply returns the first row according to the given ordering (if any).

        Example:
            ```python
            latest_error = await Log.first_or_none(order_by="-created_at", level="error")
            if latest_error:
                ...
            ```
        """
        rows = await cls.filter(limit=1, order_by=order_by, _conn=_conn, **kwargs)
        return rows[0] if rows else None

    @classmethod
    async def get_or_create(cls, _conn=None, defaults=None, **lookup):
        """
        Retrieve a record or create it if not exists.

        Args:
            _conn: Optional DB connection.
            **kwargs: Filter and creation fields.

        Returns:
            Tuple: (model instance, created_flag).

        Example:
            ```python
            user, created = await User.get_or_create(email="john@example.com", name="John")
            ```
        """
        
        found = await cls.filter(_conn=_conn, **lookup)
        if found:
            return found[0], False

        data = {}
        if defaults:
            data.update(defaults)
        data.update(lookup)

        created = await cls.create(_conn=_conn, **data)
        return created, True

    @classmethod
    async def update(cls, filters: dict, updates: dict, _conn=None, **kwargs):
        """
        Update records matching filters.

        Args:
            filters (dict): Filter conditions.
            updates (dict): Fields to update.
            _conn: Optional DB connection.

        Example:
            ```python
            await User.update(filters={"id": 1}, updates={"name": "Updated"})
            ```
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
            log.debug(f"SQL: {sql} PARAMS: {params}")
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
        Delete records matching filters.

        Args:
            _conn: Optional DB connection.
            **kwargs: Filter conditions.

        Example:
            ```python
            await User.delete(id=1)
            ```
        """
        kwargs.pop("_db", None)
        where_sql, params = cls._build_where_and_params(**kwargs)
        if not where_sql:
            raise ValueError("DELETE requires at least one condition")
        sql = f"DELETE FROM {cls.quote(cls.__table__)}{where_sql}"
        created_locally = _conn is None
        conn = _conn or await cls.connect()
        try:
            log.debug(f"SQL: {sql} PARAMS: {params}")
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
        Count records matching filters.

        Args:
            _conn: Optional DB connection.
            **kwargs: Filter conditions.

        Returns:
            int: Number of matching records.

        Example:
            ```python
            total = await User.count(is_active=1)
            ```
        """
        where_sql, params = cls._build_where_and_params(**kwargs)
        sql = f"SELECT COUNT(*) as cnt FROM {cls.quote(cls.__table__)}{cls._build_join_clause()}{where_sql}"
        created_locally = _conn is None
        conn = _conn or await cls.connect()
        try:
            log.debug(f"SQL: {sql} PARAMS: {params}")
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
        Check if any record matches filters.

        Args:
            _conn: Optional DB connection.
            **kwargs: Filter conditions.

        Returns:
            bool: True if at least one record exists.

        Example:
            ```python
            exists = await User.exists(email="john@example.com")
            ```
        """
        return (await cls.count(_conn=_conn, **kwargs)) > 0

    @classmethod
    def generate_create_table(cls):
        columns = []
        indexes = [] 
        foreign_keys = []

        for name, field in cls.__fields__.items():
            if isinstance(field, ForeignKey):
                columns.append(field.ddl(name))

                # add an index on every FK column (perf for 1-N/M2M lookups)
                indexes.append(f"INDEX ({cls.quote(name)})") 

                fk = (
                    f"FOREIGN KEY ({cls.quote(name)}) REFERENCES "
                    f"{cls.quote(field.to_model.__table__)}({cls.quote(field.to_field)})"
                )
                if getattr(field, "on_delete", None):
                    fk += f" ON DELETE {field.on_delete.upper()}"
                if getattr(field, "on_update", None):
                    fk += f" ON UPDATE {field.on_update.upper()}"
                foreign_keys.append(fk)

                # dependency for topo-order
                cls.__dependencies__ = getattr(cls, '__dependencies__', set())
                cls.__dependencies__.add(field.to_model.__table__)
            else:
                columns.append(field.ddl(name))

        # include indexes between columns and FKs
        all_defs = columns + indexes + foreign_keys
        return (
            f"CREATE TABLE IF NOT EXISTS {cls.quote(cls.__table__)} (\n  "
            + ",\n  ".join(all_defs)
            + "\n);"
        )



    @classmethod
    def join(cls, other_model, on: list, join_type="INNER"):
        """
        Create a joined model combining fields from two models.

        Args:
            other_model: The model to join with.
            on (list): Two Field objects defining join condition.
            join_type (str): SQL join type ("INNER", "LEFT", etc.).

        Returns:
            New model class with combined fields.

        Example:
            ```python
            Joined = User.join(MetaUser, on=[User.id, MetaUser.user_id])
            result = await Joined.all()
            ```
        """
        if not isinstance(on, list) or len(on) != 2:
            raise ValueError("on must be a list of two fields")
        left, right = on
        if not hasattr(left, "model") or not hasattr(right, "model"):
            raise ValueError("on must contain Field objects from the models")

        new_cls = type(
            f"{cls.__name__}Join{other_model.__name__}",
            (cls,),
            {}
        )
        new_cls.__fields__ = {**cls.__fields__, **other_model.__fields__}
        new_cls.__joins__ = getattr(cls, "__joins__", []) + [(other_model, on, join_type)]
        new_cls.__table__ = cls.__table__ 
        return new_cls


    @classmethod
    def _build_join_clause(cls):
        joins_sql = ""
        for model, on, join_type in getattr(cls, "__joins__", []):
            left, right = on
            joins_sql += (
                f" {join_type} JOIN {model.quote(model.__table__)} "
                f"ON {left.model.quote(left.model.__table__)}.{left.model.quote(left.name)} "
                f"= {right.model.quote(right.model.__table__)}.{right.model.quote(right.name)}"
            )
        return joins_sql
