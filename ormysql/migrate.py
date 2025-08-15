import inspect
import importlib

from ormysql.base import BaseModel
from .db import DB

# ----------------------
# Models container
# ----------------------

MODELS = []

def _register(*models):
    """
    Register models explicitly.

    Usage:
        from app.models import User, MetaUser
        from ormysql.migrate import register, run

        register(User, MetaUser)
        await run()
    """
    global MODELS
    MODELS = list(models)

def collect_models():
    """
    Auto-detect the caller module and collect all model classes
    (subclasses of BaseModel) defined there.

    Useful when you want to avoid manual registration and your models
    live in the same module that calls `collect_models()`.

    Usage:
        # in app/models.py
        class User(BaseModel): ...
        class MetaUser(BaseModel): ...

        # still in app/models.py
        from ormysql.migrate import collect_models, run
        collect_models()
        await run()
    """
    global MODELS

    frame = inspect.stack()[1]
    module = inspect.getmodule(frame[0])
    if not module:
        raise RuntimeError("Can't auto-detect caller module.")

    mod = importlib.import_module(module.__name__)
    found = []
    for name, obj in inspect.getmembers(mod):
        # collect concrete BaseModel subclasses only
        if inspect.isclass(obj) and issubclass(obj, BaseModel) and obj is not BaseModel:
            found.append(obj)

    MODELS = found

# ----------------------
# Topological sort by FK dependencies
# ----------------------

def sort_models_by_dependencies(models):
    """
    Sort models so that referenced (dependency) tables are created first.

    This relies on each model having `__dependencies__` populated,
    which is done when `generate_create_table()` is called.

    Args:
        models (list[type[BaseModel]]): models to order

    Returns:
        list[type[BaseModel]]: models in dependency-safe order

    Internal idea:
        - DFS over `__dependencies__` (set of table names)
        - Map table name -> model, then append post-order

    Example:
        ordered = sort_models_by_dependencies([MetaUser, User])
        # ensures User table comes before MetaUser if MetaUser FK -> User
    """
    result = []
    visited = set()

    def visit(model):
        if model in visited:
            return
        for dep in getattr(model, '__dependencies__', set()):
            dep_model = next((m for m in models if m.__table__ == dep), None)
            if dep_model:
                visit(dep_model)
        visited.add(model)
        result.append(model)

    for m in models:
        visit(m)

    return result

# ----------------------
# Run migrations (create tables if not exist)
# ----------------------

async def run():
    """
    Apply CREATE TABLE statements for all registered/collected models
    in a dependency-safe order.

    Steps:
        1) Ensure MODELS is not empty (use `register()` or `collect_models()` first).
        2) Call `generate_create_table()` on each model to populate `__dependencies__`.
        3) Sort models by dependencies via `sort_models_by_dependencies`.
        4) Execute each model's CREATE TABLE DDL with aiomysql.

    Requirements:
        - Call `DB.connect(...)` beforehand to configure the DB connection.
        - Each model must define fields using Field/ForeignKey so that
          `generate_create_table()` produces valid DDL.

    Usage:
        from ormysql.base import DB
        from ormysql.migrate import register, run
        from app.models import User, MetaUser

        DB.connect(host="127.0.0.1", port=3306, user="root", password="pwd", db="mydb")
        register(User, MetaUser)
        await run()
    """
    if not MODELS:
        print("[warn] No models found. Call `register()` or `collect_models()` first.")
        return

    for model in MODELS:
        model.generate_create_table()

    sorted_models = sort_models_by_dependencies(MODELS)

    conn = await DB.conn()
    try:
        async with conn.cursor() as cur:
            await cur.execute("START TRANSACTION")
            for model in sorted_models:
                ddl = model.generate_create_table()
                print(f"[apply] {model.__table__}")
                await cur.execute(ddl)
            await conn.commit()
    except Exception:
        await conn.rollback()
        raise
    finally:
        await DB.release(conn)
