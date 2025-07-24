import inspect
import importlib

from mysql_orm.base import BaseModel, DB

# ----------------------
# Контейнер моделей
# ----------------------

MODELS = []

def register(*models):
    global MODELS
    MODELS = list(models)

def collect_models():
    """
    Автоматически определяет вызывающий модуль и ищет в нём все модели.
    """
    global MODELS

    frame = inspect.stack()[1]
    module = inspect.getmodule(frame[0])
    if not module:
        raise RuntimeError("Can't auto-detect caller module.")

    mod = importlib.import_module(module.__name__)
    found = []
    for name, obj in inspect.getmembers(mod):
        if inspect.isclass(obj) and issubclass(obj, BaseModel) and obj is not BaseModel:
            found.append(obj)

    MODELS = found

# ----------------------
# Сортировка моделей по зависимостям
# ----------------------

def sort_models_by_dependencies(models):
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
# Запуск миграций
# ----------------------

async def run():
    if not MODELS:
        print("[warn] No models found. Call `register()` or `collect_models()` first.")
        return

    # Вызываем generate_create_table чтобы заполнить __dependencies__
    for model in MODELS:
        model.generate_create_table()

    sorted_models = sort_models_by_dependencies(MODELS)

    for model in sorted_models:
        ddl = model.generate_create_table()
        print(f"[apply] {model.__table__}")
        conn = await DB.conn()
        async with conn.cursor() as cur:
            await cur.execute(ddl)
        await conn.ensure_closed()
