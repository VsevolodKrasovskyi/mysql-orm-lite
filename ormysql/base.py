import re, sys
from .fields import Field, ManyToMany
from .db import DB
from .query import QueryMixin
from .relations import ManyToManyManager, _AwaitableList


class ModelMeta(type):
    def __new__(cls, name, bases, attrs):
        fields = {k: v for k, v in attrs.items() if isinstance(v, Field)}
        meta = attrs.get('Meta', None)
        snake = cls.camel_to_snake(name)
        table = getattr(meta, 'table', snake)

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
        new_cls.__m2m_cache__ = {}

        if meta:
            m2m_map = {
                attr_name: getattr(meta, attr_name)
                for attr_name in dir(meta)
                if not attr_name.startswith("_") and isinstance(getattr(meta, attr_name), ManyToMany)
            }
            for attr_name, m2m in m2m_map.items():
                cls._install_m2m(new_cls, attr_name, m2m)

        return new_cls

    @staticmethod
    def camel_to_snake(name: str) -> str:
        name = re.sub(r'(?<!^)(?=[A-Z])', '_', name)
        return name.lower()
    
    @classmethod
    def _install_m2m(cls, owner_model, base_attr_name: str, m2m: ManyToMany):
        module = sys.modules[owner_model.__module__]
        target_ref = m2m.target_model   
        through_ref = m2m.through      

        if hasattr(owner_model, base_attr_name) or hasattr(owner_model, f"{base_attr_name}_rel"):
            raise AttributeError(
                f"Attribute name '{base_attr_name}' or '{base_attr_name}_rel' is reserved for ManyToMany on {owner_model.__name__}"
            )

        def _resolve_now():
            cache_key = ("m2m", base_attr_name)
            if not hasattr(owner_model, "__m2m_cache__"):
                owner_model.__m2m_cache__ = {}
            if cache_key in owner_model.__m2m_cache__:
                return owner_model.__m2m_cache__[cache_key]

            target_model = target_ref if isinstance(target_ref, type) else getattr(module, target_ref)
            through_model = through_ref if isinstance(through_ref, type) else getattr(module, through_ref)

            def find_fk(through, model):

                for fname, fobj in through.__fields__.items():
                    if getattr(fobj, "to_model", None) is model:
                        return fname
                guess = cls.camel_to_snake(model.__name__) + "_id"
                if guess in through.__fields__:
                    return guess
                raise RuntimeError(f"FK not found in {through.__name__} for {model.__name__}")

            self_fk   = find_fk(through_model, owner_model)
            target_fk = find_fk(through_model, target_model)

            target_attr = cls.camel_to_snake(target_model.__name__).split("_")[-1]

            owner_model.__m2m_cache__[cache_key] = (target_model, through_model, self_fk, target_fk, target_attr)
            return owner_model.__m2m_cache__[cache_key]

        def _get_manager(self):
            return ManyToManyManager(self, _resolve_now)
        
        def _get_rel(self):
            async def _coro():
                mgr = _get_manager(self)
                return await mgr.through()
            return _AwaitableList(_coro())

        setattr(owner_model, base_attr_name, property(_get_manager))
        setattr(owner_model, f"{base_attr_name}_rel", property(_get_rel))


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
