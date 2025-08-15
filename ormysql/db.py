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
        """Store DB config and autoclose option."""
        cls._config = dict(kwargs)
        cls._config['autocommit'] = kwargs.get('autocommit', False)
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

        try:
            cls._pool = await aiomysql.create_pool(**cfg, minsize=1, maxsize=10)
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

                cls._pool = await aiomysql.create_pool(**cfg, minsize=1, maxsize=10)
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
        """Reuse a single connection for multiple operations (no explicit transaction)."""
        conn = await cls.conn()
        try:
            yield conn
        finally:
            await cls.release(conn)

    @classmethod
    @asynccontextmanager
    async def transaction(cls):
        """
        ACID transaction:
          START TRANSACTION -> yield -> COMMIT / ROLLBACK
        Работает независимо от глобального autocommit.
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
