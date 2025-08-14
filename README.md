# MySQL ORM Lite — Documentation

A tiny asynchronous ORM for MySQL built on top of `aiomysql`. It aims to stay minimal, readable, and fast, while giving you control over SQL and connections.

---

## Features at a glance

* 🔌 **Connection pool** via `aiomysql.create_pool()`
* 🧱 **Simple models** with fields and `ForeignKey`
* 🗂️ **Auto table creation** (idempotent migrations)
* 🧰 **CRUD**: `create`, `filter`, `get`, `update`, `delete`, `count`, `exists`
* 🔎 **Query helpers**: `order_by`, `limit`, `offset`, and extended filters `__gte`, `__lte`, `__like`, `__in`
* 🔄 **Transactions & sessions** with `async with DB.transaction()/DB.session()`
* ✅ **Safe**: parameterized SQL, whitelisted columns in `ORDER BY`
* 📴 **Auto-close pool** on process exit (by default)

---

## Requirements & install

* Python 3.10+
* MySQL 5.7+ / 8.0+
* `aiomysql`

```bash
pip install aiomysql
```

---

## Quick start

```python
from ormysql.base import BaseModel, DB
from ormysql.fields import Integer, String, ForeignKey, DateTime
from ormysql import migrate
import asyncio

# 1) Define models
class User(BaseModel):
    id = Integer(pk=True)
    name = String(length=100)
    email = String(unique=True)

    class Meta:
        table = "users"  # optional (default: snake_case + 's')

class MetaUser(BaseModel):
    user_id = ForeignKey(User)
    description = String()
    image = String()
    date = DateTime(default="CURRENT_TIMESTAMP")

# 2) Collect models for migrations
migrate.collect_models()

# 3) Configure DB (pool is created lazily on first use)
DB.connect(
    host="localhost",
    user="root",
    password="root",
    db="test",
    autocommit=True,    # server-side autocommit
    # autoclose=True    # auto-close pool at process exit (default = True)
)

async def main():
    # 4) Apply migrations (CREATE TABLE IF NOT EXISTS)
    await migrate.run()

    # 5) CRUD examples
    user, created = await User.get_or_create(name="Alice", email="alice@example.com")
    print(user, created)

    users = await User.all(order_by="-id", limit=10)
    for u in users:
        print(u)

    meta = await MetaUser.get(user_id=user.id, default=None, raise_multiple=False)
    print(meta)

asyncio.run(main())
```

---

## Defining models

Models subclass `BaseModel` and declare fields. Supported field classes (in `fields.py`):
`Integer`, `String(length=...)`, `Text`, `Boolean`, `DateTime`, `Float`, `Decimal(precision, scale)`, `ForeignKey(Model, to_field="id")`.

```python
class User(BaseModel):
    id = Integer(pk=True)         # PRIMARY KEY (AUTO_INCREMENT if name is 'id' and INT)
    name = String(length=100)     # VARCHAR(100) NOT NULL
    email = String(unique=True)   # UNIQUE

    class Meta:
        table = "users"           # override table name (optional)
```

**Table name resolution**: by default `CamelCase` → `snake_case` + `s` (e.g., `MetaUser` → `meta_users`).

---

## DB configuration & pool

Call `DB.connect(...)` once at startup. The pool is **lazy** (created on first use). If the database does not exist, it’s created automatically.

```python
DB.connect(
    host="localhost",
    user="root",
    password="root",
    db="test",
    autocommit=True,   # or False: ORM will commit after DML when it created the connection
    autoclose=True     # default: True, auto-closes pool on process exit (atexit)
)
```

### Sessions & transactions

* **Session**: reuse a single connection for multiple operations (no explicit transaction).

```python
async with DB.session() as conn:
    rows = await User.filter(order_by="-id", limit=5, _conn=conn)
    total = await User.count(_conn=conn)
```

* **Transaction (ACID)**: guarantees `START TRANSACTION` → `COMMIT` / `ROLLBACK`.

```python
async with DB.transaction() as conn:
    u = await User.create(name="X", email="x@x.com", _conn=conn)
    await MetaUser.create(user_id=u.id, description="...", image="...", _conn=conn)
```

All CRUD methods accept optional `_conn`, so you can batch operations in one session/transaction for speed and consistency.

---

## Migrations (idempotent)

A minimal migration helper that generates `CREATE TABLE IF NOT EXISTS` by introspecting your models.

```python
from ormysql import migrate

migrate.collect_models()  # scan current module for BaseModel subclasses
await migrate.run()       # apply DDL in dependency order
```

> This is intentionally minimal: no schema versioning or ALTER flows. Perfect for small projects and experiments.

---

## CRUD API

### Create

```python
user = await User.create(name="Alice", email="alice@example.com")
# If autocommit=False, ORM commits automatically after DML when it created the connection.
```

### Read: `all`, `filter`, `get`

All readers support:

* `order_by="field"` (ASC) or `order_by="-field"` (DESC)
* pagination: `limit`, `offset`
* extended filters (see below)

```python
# All users ordered by name
users = await User.all(order_by="name")

# Last 10 users by id
users = await User.all(order_by="-id", limit=10)

# Equality filters
users = await User.filter(name="Alice", email="alice@example.com")

# Extended operators: __gte, __lte, __like, __in
adults   = await User.filter(age__gte=18)
pattern  = await User.filter(name__like="%Al%")
subset   = await User.filter(id__in=[1, 2, 3])
```

#### `get()` — robust single-row fetch

```python
# Strict mode (default): exactly one row expected
user = await User.get(id=1)                  # 0 or >1 -> LookupError

# Graceful fallback: 0 rows → default (e.g., None)
maybe = await User.get(email="x@x.com", default=None)

# Allow multiple; pick the “first” with optional ordering
latest = await User.get(name="Alice", raise_multiple=False, order_by="-id")
```

### Update

```python
await User.update(
    filters={"id": 1},             # supports extended operators, e.g., {"age__gte": 18}
    updates={"name": "Alicia"}
)
```

### Delete

```python
await User.delete(id=1)
# Safety: at least one condition is required; deleting without WHERE raises ValueError.
```

### Aggregate helpers

```python
total  = await User.count()
exists = await User.exists(email="alice@example.com")
```

---

## Extended filters

You can express basic operators right in kwargs:

* `field__gte=value`  → `field >= %s`
* `field__lte=value`  → `field <= %s`
* `field__like=value` → `field LIKE %s`
* `field__in=[...]`   → `field IN (%s, %s, ...)` (empty lists become `1=0`)

Example:

```python
users = await User.filter(
    age__gte=18,
    name__like="%Al%",
    id__in=[1, 3, 9],
    order_by="-id",
    limit=20, offset=0
)
```

---

## Ordering & safety

* `order_by="name"` sorts ascending, `order_by="-name"` descending.
* The ORM validates that the column exists in the model before injecting it into SQL (prevents SQL injection in `ORDER BY`).
* All values are passed via parameterized queries (`%s` placeholders).

---

## Transactions, commits & autocommit

* With `DB.connect(..., autocommit=True)`, MySQL commits DML automatically.
* With `autocommit=False`, the ORM **commits automatically** after `INSERT/UPDATE/DELETE` when it created the connection itself.
* For multi-step atomic flows, use `async with DB.transaction()` and pass `_conn` to every call inside the block.

---

## Performance

* **Pooling** avoids reconnect costs (TCP handshake, auth) on every query.
* **Session/transaction context** reduces `acquire/release` overhead and lets you control when to commit.
* **Minimal abstraction**: queries are straightforward and fast.

---

## Common pitfalls & notes

* **“Table '…' already exists”** warnings during migrations are normal with idempotent `CREATE TABLE IF NOT EXISTS`.
* **“Event loop is closed”** on shutdown: mitigated by **auto-close** (default). If you set `autoclose=False`, call `await DB.close()` before exiting.
* Deleting without conditions is blocked (raises `ValueError`) to avoid accidental full-table wipes.
* `ForeignKey` enforces constraints in DDL. Higher-level relation helpers (e.g., `select_related`) are on the roadmap; for now, do second queries manually.

---

## Example: transaction with multiple models

```python
async with DB.transaction() as conn:
    user = await User.create(name="Bob", email="bob@example.com", _conn=conn)
    await MetaUser.create(
        user_id=user.id,
        description="Bob’s profile",
        image="avatar_bob.png",
        _conn=conn
    )
# if any step fails → everything is rolled back
```

---

## Example: batched reads in a single session

```python
async with DB.session() as conn:
    latest = await User.all(order_by="-id", limit=5, _conn=conn)
    total  = await User.count(_conn=conn)
    a_ids  = [u.id for u in await User.filter(name__like="A%", _conn=conn)]
```

---

## Roadmap (nice-to-have)

* Relation mapping helpers (`select_related`, lazy/eager)
* Index definitions (including composite)
* Model-level validation
* SQL query logging
* Simple CLI (apply/revert migrations, inspect schema)
* Test utilities (temporary DB fixtures)

---

## FAQ

**Do I need to call `DB.close()`?**
By default **no** — `autoclose=True` closes the pool on process exit. If you disable it, call `await DB.close()` yourself.

**How do I ensure strict single-row fetch?**
Use `await Model.get(...)` with default settings (`raise_multiple=True`). It raises if 0 or >1 rows are found.

**Can I pass multiple columns to `get()`?**
Yes. `await User.get(name="Alice", email="alice@example.com")` → `WHERE name = %s AND email = %s LIMIT 1`.

**How do I make it faster?**
Batch related queries inside `DB.session()` or `DB.transaction()` and pass `_conn=conn` to each call.
