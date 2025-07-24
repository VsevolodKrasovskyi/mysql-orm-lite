import aiomysql
import re
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

    @classmethod
    def connect(cls, **kwargs):
        cls._config = kwargs

    @classmethod
    async def conn(cls):
        if not cls._config:
            raise ConnectionError("Call `DB.connect(...)` first to configure DB connection.")

        try:
            return await aiomysql.connect(**cls._config)

        except Exception as e:
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

    def __init__(self, **kwargs):
        for field in self.__fields__:
            setattr(self, field, kwargs.get(field))

    def to_dict(self):
        return {k: getattr(self, k) for k in self.__fields__}
    
    def __repr__ (self):
        return f"<{self.__class__.__name__} {self.to_dict()}>"

    @staticmethod
    def quote(name: str) -> str:
        return f"`{name}`"

    @classmethod
    async def connect(cls):
        return await DB.conn()
    
    @classmethod
    async def create(cls, **kwargs):
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
    async def all(cls, limit=None, **kwargs):
        kwargs.pop("_db", None)
        sql = f"SELECT * FROM {cls.quote(cls.__table__)}"
        if limit:
            sql += f" LIMIT {int(limit)}"
        conn = await cls.connect()
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(sql)
            rows = await cur.fetchall()
        await conn.ensure_closed()
        return [cls(**row) for row in rows]

    @classmethod
    async def filter(cls, limit=None, **kwargs):
        kwargs.pop("_db", None)
        keys = list(kwargs.keys())
        where = " AND ".join([f"{cls.quote(k)} = %s" for k in keys])
        sql = f"SELECT * FROM {cls.quote(cls.__table__)} WHERE {where}"
        if limit:
            sql += f" LIMIT {int(limit)}"
        conn = await cls.connect()
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(sql, tuple(kwargs[k] for k in keys))
            rows = await cur.fetchall()
        await conn.ensure_closed()
        return [cls(**row) for row in rows]

    @classmethod
    async def get_or_create(cls, **kwargs):
        kwargs.pop("_db", None)
        found = await cls.filter(**kwargs)
        if found:
            return found[0], False
        created = await cls.create(**kwargs)
        return created, True

    @classmethod
    async def update(cls, filters: dict, updates: dict, **kwargs):
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
