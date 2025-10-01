import asyncio
import atexit
import aiomysql
from contextlib import asynccontextmanager

class DB:
    _config = None
    _pool = None
    _auto_close_enabled = False
    

    @classmethod
    def connect(cls, autoclose: bool = True, **kwargs):
        """
        ## Configure the database connection pool (no network I/O here).

        This only stores settings; the pool is created lazily on first use
        (e.g., when `DB.conn()` or any ORM call is executed). If the target
        database does not exist, it will be created automatically.

        ### Required kwargs:
        - host (str)       : MySQL host, e.g. "127.0.0.1"
        - user (str)       : DB user
        - password (str)   : DB password
        - db (str)         : Database name

        ### Optional kwargs:
        - port (int)             : Default 3306
        - autocommit (bool)      : Default True (server-side autocommit)
        - Any `aiomysql.create_pool(...)` options, e.g.:
            minsize, maxsize, pool_recycle, connect_timeout, charset, autoping, etc.
        Parameter (not in **kwargs):
        - autoclose (bool) : Default True. If True, an atexit hook will
            gracefully close the pool on process exit.

        ### Autocommit semantics:
        - autocommit=True  : MySQL commits DML automatically.
        - autocommit=False : When the ORM created the connection itself,
            it will COMMIT automatically after INSERT/UPDATE/DELETE.
            For multi-step atomic flows, use `async with DB.transaction()`.

        ### Example:
        ```python
            DB.connect(
                host="127.0.0.1",
                user="root",
                password="root",
                db="test",
                port=3306,          # optional
                autocommit=True,    # optional
                autoclose=True,     # optional (param, not in **kwargs)
                minsize=1, maxsize=10  # optional pool settings
            )
        ```
        """
        cls._config = dict(kwargs)
        cls._config['autocommit'] = kwargs.get('autocommit', True)
        cls._config['autoclose'] = autoclose

        if autoclose:
            cls._enable_auto_close()

    @classmethod
    def _enable_auto_close(cls):
        if cls._auto_close_enabled:
            return
        cls._auto_close_enabled = True

        def _shutdown():
            try:
                asyncio.run(cls.close())
            except RuntimeError:
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

        cfg = dict(cls._config)
        cfg.pop("autoclose", None)
        minsize = cfg.pop("minsize", 1)
        maxsize = cfg.pop("maxsize", 10)

        try:
            cls._pool = await aiomysql.create_pool(**cfg, minsize=minsize, maxsize=maxsize)
        except Exception as e:
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

                cls._pool = await aiomysql.create_pool(**cfg, minsize=minsize, maxsize=maxsize)
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
        pool = await cls.pool()
        pool.release(conn)

    @classmethod
    async def close(cls):
        if cls._pool is not None:
            cls._pool.close()
            await cls._pool.wait_closed()
            cls._pool = None

    @classmethod
    @asynccontextmanager
    async def session(cls):
        """
        ## Acquire **one pooled connection** and reuse it across multiple ORM calls.

        This context does **NOT** start a transaction; autocommit rules still apply.
        Use it to batch several reads/writes on the same connection (fewer pool
        checkouts) or to set per-connection options for the duration of the block.

        ### Usage:
         ```python
            async with DB.session() as conn:
                # All calls below use the SAME connection.
                alice = await User.create(username="alice", _conn=conn)
                await Bonus.create(name="Welcome", points=10, _conn=conn)

                # Reads on the same connection
                users = await User.filter(username__like="a%", _conn=conn)
                again = await User.get(id=alice.id, _conn=conn)
        ```
        ### Notes:
        - Always pass `_conn=conn` into ORM methods inside this context;
        otherwise they will grab another connection from the pool.
        - If you need ACID guarantees, use `DB.transaction()` instead.
        - Do not keep or reuse `conn` after the context exits.
        """
        conn = await cls.conn()
        try:
            yield conn
            if not cls.is_autocommit():
                await conn.commit()
        except Exception:
            if not cls.is_autocommit():
                await conn.rollback()
            raise
        finally:
            await cls.release(conn)

    @classmethod
    @asynccontextmanager
    async def transaction(cls):
        """
        ## Open an **ACID transaction** on a pooled connection.

        ### Flow:
        START TRANSACTION
            -> yield `conn` (do your work)
        COMMIT on normal exit / ROLLBACK if an exception escapes.

        ### Example (commit):
         ```python
            async with DB.transaction() as conn:
                u = await User.create(username="bob", _conn=conn)
                await UserHasProduct.create(user_id=u.id, bonus_id=1, total_amount=3, _conn=conn)
                # no exception -> COMMIT
        ```

        ### Example (rollback):
         ```python
            try:
                async with DB.transaction() as conn:
                    await User.create(username="charlie", _conn=conn)
                    raise RuntimeError("boom")
            except RuntimeError:
                pass  # everything inside the block was rolled back
         ```

        ### Example (typical invariant: transfer funds atomically):
        ```python
            async with DB.transaction() as conn:
                a = await Account.get(id=1, _conn=conn)
                b = await Account.get(id=2, _conn=conn)
                if a.balance < 100:
                    raise ValueError("insufficient funds")
                await Account.update(id=a.id, balance=a.balance - 100, _conn=conn)
                await Account.update(id=b.id, balance=b.balance + 100, _conn=conn)
        ```

        ### Notes:
        - Always pass `_conn=conn` into EVERY ORM call inside the block so they
        participate in the same transaction.
        - Nested transactions (savepoints) are not supported yet.
        - Global autocommit does not matter; this context explicitly issues
        BEGIN/COMMIT/ROLLBACK.
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
