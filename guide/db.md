# DB

Low-level database utilities: configuration, connection pooling, sessions, and transactions.

`DB` is a thin wrapper around **aiomysql** that provides:

* Lazy **connection pool** creation
* Optional **database auto-creation** if it doesn't exist
* Safe **autocommit** semantics
* **Session** helper to reuse one pooled connection
* **Transaction** helper with automatic COMMIT/ROLLBACK
* Clean shutdown via an `atexit` hook (autoclose)

---

## Configure (`DB.connect`)

```python
from ormysql.db import DB

DB.connect(
  host="127.0.0.1",
  user="root",
  password="root",
  db="test",
  port=3306,           # optional (default 3306)
  autocommit=True,     # optional; server-side autocommit
  autoclose=True,      # optional; register atexit pool close
  # any aiomysql.create_pool(...) options:
  minsize=1, maxsize=10, pool_recycle=3600, connect_timeout=10, autoping=True,
)
```

**Key points**

* `DB.connect(...)` stores config only. **No network I/O** happens here.
* The pool is created **lazily** on first use (e.g. `DB.conn()` or any ORM call).
* If the target database does **not** exist, it will be **created automatically** on first pool creation.

### Autocommit semantics

* `autocommit=True` → MySQL commits each DML automatically.
* `autocommit=False` → When the ORM opens connections by itself, it will commit automatically after `INSERT/UPDATE/DELETE`.
  For multi-step atomic flows, use `async with DB.transaction():`.

### Autoclose semantics

* `autoclose=True` (default) registers an `atexit` hook that gracefully closes the pool on process exit.

---

## Pool lifecycle

* **Create**: implicit on first use (`await DB.pool()` or `await DB.conn()`).
* **Acquire** connection: `conn = await DB.conn()`
* **Release** connection: `await DB.release(conn)`
* **Close** pool: `await DB.close()` (normally not needed; done by `atexit` when `autoclose=True`).

You rarely need `conn()`/`release()` directly — prefer `DB.session()` or `DB.transaction()` below.

---

## Sessions (`DB.session`)

> Acquire **one pooled connection** and reuse it across multiple ORM calls.
> Does **NOT** start a transaction; autocommit rules still apply.

```python
from ormysql.db import DB
from app.models import User, Bonus

async with DB.session() as conn:
    # all calls below share the SAME connection
    alice = await User.create(username="alice", _conn=conn)
    await Bonus.create(name="Welcome", points=10, _conn=conn)

    users = await User.filter(username__like="a%", _conn=conn)
    again = await User.get_or_none(id=alice.id, _conn=conn)
```

**Notes**

* Always pass `_conn=conn` into ORM methods **inside** the session block; otherwise a new connection will be acquired from the pool.
* Use sessions for **batching** calls (fewer pool roundtrips) or when you need per‑connection settings.
* **No ACID boundary** here; for atomicity use a transaction.

---

## Transactions (`DB.transaction`)

> Open an **ACID transaction** on a pooled connection.
> `COMMIT` on normal exit, `ROLLBACK` if an exception escapes the block.

```python
from ormysql.db import DB
from app.models import User, UsersHasProduct

# Commit example
async with DB.transaction() as conn:
    u = await User.create(username="bob", _conn=conn)
    await UsersHasProduct.create(user_id=u.id, bonus_name="VIP", total_amount=1, _conn=conn)

# Rollback example
try:
    async with DB.transaction() as conn:
        await User.create(username="charlie", _conn=conn)
        raise RuntimeError("boom")
except RuntimeError:
    pass  # everything inside was rolled back
```

**Atomic pattern (invariants)**

```python
async with DB.transaction() as conn:
    a = await Account.get_or_none(id=1, _conn=conn)
    b = await Account.get_or_none(id=2, _conn=conn)
    if a.balance < 100:
        raise ValueError("insufficient funds")
    await Account.update({"id": a.id}, {"balance": a.balance - 100}, _conn=conn)
    await Account.update({"id": b.id}, {"balance": b.balance + 100}, _conn=conn)
```

**Rules**

* Pass `_conn=conn` to **every** ORM call inside the block so they participate in the same transaction.
* Nested transactions / savepoints: **not supported (yet)**.
* Global `autocommit` does **not** matter inside `DB.transaction()`; the context explicitly issues `BEGIN/COMMIT/ROLLBACK`.

---

## Using `_conn` with the ORM

All ORM methods accept optional `_conn`:

```python
await User.create(..., _conn=conn)
await User.filter(..., _conn=conn)
await User.update(filters, updates, _conn=conn)
await User.delete(..., _conn=conn)
```

**Why it matters**

* When you pass `_conn`, your call **reuses** the connection (Session/Transaction).
* When you **don’t** pass `_conn`, the ORM **acquires/releases** a connection automatically.

---

## Database auto‑creation

On the first attempt to create the pool, if MySQL returns *“Unknown database”* for the configured `db`, `DB` will:

1. Connect **without** the `db` argument,
2. Execute `CREATE DATABASE IF NOT EXISTS` db,
3. Retry pool creation with the original config.

This helps in CI/first boot scenarios. You still need a user with permissions to create databases.

---

## Clean shutdown

With `autoclose=True` (default), `DB` registers an `atexit` hook that runs:

```python
await DB.close()
```

This closes the pool and waits for all connections to finish.

---

## Best practices

* **Short-lived tasks**: `autocommit=True` + direct ORM calls (no session/transaction) keeps things simple.
* **Batch operations (no strict atomicity)**: use `DB.session()` and pass `_conn` to save pool overhead.
* **Atomic multi-step flows**: use `DB.transaction()` and pass `_conn` everywhere inside the block.
* Always keep model operations **idempotent** on webhook/worker paths (Stripe, etc.), and handle duplicates in a transaction.
* Avoid keeping a connection beyond the context block; let the pool manage it.

---

## Troubleshooting

**“Call `DB.connect(...)` first.”**
You used `DB.pool()/DB.conn()` before configuring the connection. Call `DB.connect(...)` once at boot.

**`ModuleNotFoundError: ... db`**
Run from the project root or export `PYTHONPATH` so that `db` (your models package) is importable.

**Deadlocks / long locks**
Keep transactions short; only group what must be atomic. Consider appropriate isolation and indexes.

**Too many connections**
Tune `minsize/maxsize` for the pool. Avoid opening transactions that wait on external I/O.

---

## Cheatsheet

```python
# Global config (no network I/O yet)
DB.connect(host="127.0.0.1", user="root", password="root", db="test", autocommit=True)

# One-off ORM call (will acquire/release a pooled connection)
user = await User.create(name="Alice")

# Reuse one connection across multiple calls (no transaction)
async with DB.session() as conn:
    await User.create(name="Bob", _conn=conn)
    await User.create(name="Eve", _conn=conn)

# Atomic block
async with DB.transaction() as conn:
    await Wallet.update({"id": 1}, {"amount": 90}, _conn=conn)
    await Wallet.update({"id": 2}, {"amount": 110}, _conn=conn)
```
