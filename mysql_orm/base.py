import aiomysql
import re
from .fields import Field, ForeignKey


class ModelMeta(type):
    """
    Metaclass that:
      - Collects declared Field instances into __fields__
      - Resolves table name to __table__ (from Meta.table or snake_case + 's')

    Usage:
        class User(BaseModel):
            id = IntegerField(primary_key=True)
            name = CharField(max_length=255)

            class Meta:
                table = "users"  # optional; otherwise 'user' -> 'users'
    """
    def __new__(cls, name, bases, attrs):
        # Collect only attributes that are Field instances
        fields = {k: v for k, v in attrs.items() if isinstance(v, Field)}
        meta = attrs.get('Meta', None)
        snake = cls.camel_to_snake(name)
        table = getattr(meta, 'table', f"{snake}s")
        attrs['__fields__'] = fields
        attrs['__table__'] = table
        return super().__new__(cls, name, bases, attrs)

    @staticmethod
    def camel_to_snake(name: str) -> str:
        """
        Convert CamelCase to snake_case.

        Example:
            camel_to_snake("MetaUser") -> "meta_user"
        """
        s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
        return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()


class DB:
    """
    Simple DB connection holder for aiomysql.
    You must call DB.connect(...) once before using models.

    Example:
        DB.connect(host="127.0.0.1", port=3306, user="root", password="pwd", db="mydb")
        # later inside a model method:
        conn = await DB.conn()
    """
    _config = None

    @classmethod
    def connect(cls, **kwargs):
        """
        Store connection params (host, port, user, password, db, etc.).

        Example:
        ```
        DB.connect(host="127.0.0.1", port=3306, user="root", password="pwd", db="mydb")
        ```
        """
        cls._config = kwargs

    @classmethod
    async def conn(cls):
        """
        Open and return a new aiomysql connection using stored config.
        If the target database does not exist, it tries to create it.

        Returns:
            aiomysql.Connection

        Note:
            The caller is responsible for closing the connection via
            `await conn.ensure_closed()`.

        Example:
            conn = await DB.conn()
            async with conn.cursor() as cur:
                await cur.execute("SELECT 1")
            await conn.ensure_closed()
        """
        if not cls._config:
            raise ConnectionError("Call `DB.connect(...)` first to configure DB connection.")

        try:
            return await aiomysql.connect(**cls._config)

        except Exception as e:
            # Auto-create database if missing
            if hasattr(e, 'args') and isinstance(e.args, tuple) and 'Unknown database' in str(e.args[1]):
                db_name = cls._config.get("db")
                print(f"[info] Database '{db_name}' not found, creating it...")

                temp_config = dict(cls._config)
                temp_config.pop("db", None)
                conn = await aiomysql.connect(**temp_config)
                async with conn.cursor() as cur:
                    await cur.execute(f"CREATE DATABASE IF NOT EXISTS `{db_name}`")
                await conn.ensure_closed()

                return await aiomysql.connect(**cls._config)

            raise ConnectionError(f"Failed to connect to DB: {e}")


class BaseModel(metaclass=ModelMeta):
    """
    Base model providing minimal CRUD operations.

    To define a model:
        class User(BaseModel):
            id = IntegerField(primary_key=True)
            name = CharField(max_length=255)
            email = CharField(max_length=255)

            class Meta:
                table = "users"  # optional

    Typical usage:
        ## CREATE
        user = await User.create(name="Alice", email="alice@example.com")

        ## READ
        all_users = await User.all()
        found = await User.filter(name="Alice")
        one = await User.get(name="Alice")  # raises if not found

        ## UPSERT-ish
        user, created = await User.get_or_create(name="Bob", email="bob@example.com")

        ## UPDATE
        await User.update(filters={"id": 1}, updates={"name": "Alicia"})

        ## DELETE
        await User.delete(id=1)

        ## DDL
        sql = User.generate_create_table()
    """

    def __init__(self, **kwargs):
        """
        Initialize instance with field values from kwargs.
        Non-provided fields default to None.

        Example:
            u = User(id=1, name="Alice")  # User.__fields__ drives which attrs are set
        """
        for field in self.__fields__:
            setattr(self, field, kwargs.get(field))

    def to_dict(self):
        """
        Convert model instance to a dict of its declared fields.

        Example:
            u.to_dict() -> {"id": 1, "name": "Alice", "email": "..."}
        """
        return {k: getattr(self, k) for k in self.__fields__}
    
    def __repr__ (self):
        """
        Debug representation.

        Example:
            print(u) -> <User {'id': 1, 'name': 'Alice', 'email': '...'}>
        """
        return f"<{self.__class__.__name__} {self.to_dict()}>"

    @staticmethod
    def quote(name: str) -> str:
        """
        Quote identifiers (table/column names) with backticks for MySQL.

        Example:
            quote("users") -> "`users`"
        """
        return f"`{name}`"

    @classmethod
    async def connect(cls):
        """
        Shortcut to DB.conn() for model methods.

        Example:
        ```
        conn = await User.connect()
        ```
        """
        return await DB.conn()
    
    @classmethod
    async def create(cls, **kwargs):
        """
        Insert a new row with the provided field values and return an instance.

        Returns:
            cls: newly created instance (NOTE: 'id' may be None unless you set it yourself)

        IMPORTANT:
            - This method does not call `conn.commit()` and does not set `lastrowid` back
              into the object. Consider adding commit and assigning `id` if needed.

        Example:
        ```
        user = await User.create(name="Alice", email="alice@example.com")
        ```
        """
        kwargs.pop("_db", None)
        keys = list(kwargs.keys())
        values = tuple(kwargs[k] for k in keys)

        fields = ", ".join(cls.quote(k) for k in keys)
        placeholders = ", ".join(["%s"] * len(keys))
        sql = f"INSERT INTO {cls.quote(cls.__table__)} ({fields}) VALUES ({placeholders})"

        conn = await cls.connect()
        async with conn.cursor() as cur:
            await cur.execute(sql, values)
        await conn.ensure_closed()
        return cls(**kwargs)

    @classmethod
    async def all(cls, limit=None, order_by=None, **kwargs):
        """
        Fetch all rows (optionally limited and ordered) and return a list of model instances.

        Args:
            limit (int|None): Optional LIMIT clause.
            order_by (str|None): Column name to order by.
                - Prefix with "-" for DESC (descending order)
                - Without prefix means ASC (ascending order)

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

        # ORDER BY
        if order_by:
            desc = order_by.startswith("-")
            col = order_by[1:] if desc else order_by
            sql += f" ORDER BY {cls.quote(col)} {'DESC' if desc else 'ASC'}"

        # LIMIT
        if limit:
            sql += f" LIMIT {int(limit)}"

        conn = await cls.connect()
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(sql)
            rows = await cur.fetchall()
        await conn.ensure_closed()
        return [cls(**row) for row in rows]


    @classmethod
    async def filter(cls, limit=None, order_by=None, **kwargs):
        """
        Fetch rows matching equality conditions and return a list of model instances.

        Args:
            limit (int|None): Optional LIMIT clause.
            order_by (str|None): Column name to order by.
                - Prefix with "-" for DESC (descending order)
                - Without prefix means ASC (ascending order)
            **kwargs: Column=value pairs for WHERE conditions.

        Examples:
            ### Users named 'Alice' ordered by registration date ascending
            ```
            users = await User.filter(name="Alice", order_by="created_at")
            ```

            ### Latest 3 posts by author_id=1 ordered by date descending
            ```
            posts = await Post.filter(author_id=1, limit=3, order_by="-created_at")
            ```

            ### Products in category 5 ordered by price ascending (cheapest first)
            ```
            products = await Product.filter(category_id=5, order_by="price")
            ```

            ### Products in category 5 ordered by price descending (most expensive first)
            ```
            products = await Product.filter(category_id=5, order_by="-price")
            ```
        """
        kwargs.pop("_db", None)
        keys = list(kwargs.keys())

        sql = f"SELECT * FROM {cls.quote(cls.__table__)}"
        if keys:
            where = " AND ".join([f"{cls.quote(k)} = %s" for k in keys])
            sql += f" WHERE {where}"

        # ORDER BY
        if order_by:
            desc = order_by.startswith("-")
            col = order_by[1:] if desc else order_by
            sql += f" ORDER BY {cls.quote(col)} {'DESC' if desc else 'ASC'}"

        # LIMIT
        if limit:
            sql += f" LIMIT {int(limit)}"

        conn = await cls.connect()
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(sql, tuple(kwargs[k] for k in keys))
            rows = await cur.fetchall()
        await conn.ensure_closed()
        return [cls(**row) for row in rows]

    
    @classmethod
    async def get(cls, **kwargs):
        """
        Return the first row matching the conditions or raise LookupError if none.

        Returns:
            cls

        Raises:
            LookupError: when no rows were found

        Example:
        ```
        user = await User.get(id=1)
        ``` 
        """
        rows = await cls.filter(limit=1, **kwargs)
        if not rows:
            raise LookupError(f"{cls.__name__}.get() no rows for {kwargs}")
        return rows[0]

    @classmethod
    async def get_or_create(cls, **kwargs):
        """
        Try to fetch by exact match; if nothing found, create a new row.

        Returns:
            (cls, bool): (instance, created_flag)

        Example:
        ```
            user, created = await User.get_or_create(name="Bob", email="bob@example.com")
            if created:
                print("New user inserted")
        ```
        """
        kwargs.pop("_db", None)
        found = await cls.filter(**kwargs)
        if found:
            return found[0], False
        created = await cls.create(**kwargs)
        return created, True

    @classmethod
    async def update(cls, filters: dict, updates: dict, **kwargs):
        """
        Update rows that match `filters` with values from `updates`.

        Args:
            filters (dict): column=value conditions for WHERE
            updates (dict): column=value pairs to SET

        Returns:
            None

        Example:
        ```
        await User.update(filters={"id": 1}, updates={"name": "Alicia"})
        ```
        """
        kwargs.pop("_db", None)
        set_clause = ", ".join([f"{cls.quote(k)} = %s" for k in updates])
        where_clause = " AND ".join([f"{cls.quote(k)} = %s" for k in filters])
        sql = f"UPDATE {cls.quote(cls.__table__)} SET {set_clause} WHERE {where_clause}"
        conn = await cls.connect()
        async with conn.cursor() as cur:
            await cur.execute(sql, tuple(updates.values()) + tuple(filters.values()))
        await conn.ensure_closed()

    @classmethod
    async def delete(cls, **kwargs):
        """
        Delete rows matching equality conditions.

        Args:
            **kwargs: column=value pairs for WHERE

        Returns:
            None

        Example:
        ```
        await User.delete(id=1)
        await User.delete(name="Alice", email="alice@example.com")
        ```
        """
        kwargs.pop("_db", None)
        keys = list(kwargs.keys())
        where_clause = " AND ".join([f"{cls.quote(k)} = %s" for k in keys])
        sql = f"DELETE FROM {cls.quote(cls.__table__)} WHERE {where_clause}"
        conn = await cls.connect()
        async with conn.cursor() as cur:
            await cur.execute(sql, tuple(kwargs[k] for k in keys))
        await conn.ensure_closed()

    @classmethod
    def generate_create_table(cls):
        """
        Generate a CREATE TABLE DDL statement based on declared fields.
        Handles ForeignKey references and remembers dependencies.

        Returns:
            str: CREATE TABLE ... SQL

        Example:
        ```
        print(User.generate_create_table())
        # -> "CREATE TABLE IF NOT EXISTS `users` (...);"
        ```
        """
        columns = []
        foreign_keys = []

        for name, field in cls.__fields__.items():
            if isinstance(field, ForeignKey):
                columns.append(field.ddl(name))
                foreign_keys.append(
                    f"FOREIGN KEY ({cls.quote(name)}) REFERENCES {cls.quote(field.to_model.__table__)}({cls.quote(field.to_field)})"
                )
                cls.__dependencies__ = getattr(cls, '__dependencies__', set())
                cls.__dependencies__.add(field.to_model.__table__)
            else:
                columns.append(field.ddl(name))

        all_defs = columns + foreign_keys
        return f"CREATE TABLE IF NOT EXISTS {cls.quote(cls.__table__)} (\n  " + ",\n  ".join(all_defs) + "\n);"
