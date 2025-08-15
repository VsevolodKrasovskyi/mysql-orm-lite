import re
from .fields import Field
from .db import DB
from .query import QueryMixin


class ModelMeta(type):
    def __new__(cls, name, bases, attrs):
        fields = {k: v for k, v in attrs.items() if isinstance(v, Field)}
        meta = attrs.get('Meta', None)
        snake = cls.camel_to_snake(name)
        table = getattr(meta, 'table', f"{snake}s")

        for field_name, field in fields.items():
            field.model = None
            field.name = field_name

        new_cls = super().__new__(cls, name, bases, attrs)

        for field_name, field in fields.items():
            field.model = new_cls
            field.name = field_name

        new_cls.__fields__ = fields
        new_cls.__table__ = table
        new_cls.__joins__ = []
        return new_cls

    @staticmethod
    def camel_to_snake(name: str) -> str:
        s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
        return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()


class BaseModel(QueryMixin, metaclass=ModelMeta):
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
        join_mode = bool(getattr(cls, "__joins__", []))

        for key, value in kwargs.items():
            if key in ("_db", "_conn"):
                continue
            if "__" in key:
                col, op = key.split("__", 1)
                cls._ensure_column(col)
                table_name = cls.__fields__[col].model.__table__ if join_mode else cls.__table__
                col_sql = f"{cls.quote(table_name)}.{cls.quote(col)}"
                if op == "gte":
                    conditions.append(f"{col_sql} >= %s")
                    params.append(value)
                elif op == "lte":
                    conditions.append(f"{col_sql} <= %s")
                    params.append(value)
                elif op == "like":
                    conditions.append(f"{col_sql} LIKE %s")
                    params.append(value)
                elif op == "in":
                    if not value:
                        conditions.append("1=0")
                    else:
                        placeholders = ", ".join(["%s"] * len(value))
                        conditions.append(f"{col_sql} IN ({placeholders})")
                        params.extend(value)
                else:
                    raise ValueError(f"Unsupported filter operator: {op}")
            else:
                cls._ensure_column(key)
                table_name = cls.__fields__[key].model.__table__ if join_mode else cls.__table__
                col_sql = f"{cls.quote(table_name)}.{cls.quote(key)}"
                conditions.append(f"{col_sql} = %s")
                params.append(value)

        where_sql = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        return where_sql, params


    @classmethod
    async def connect(cls):
        return await DB.conn()
