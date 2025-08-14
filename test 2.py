"""
TEST 2 — autocommit=False, autoclose=False
Check manual commit() and manual pool closure.
"""

import asyncio
from ormysql.base import BaseModel, DB
from ormysql.fields import Integer, String, ForeignKey, DateTime
from ormysql import migrate


# ---------- Models ----------
class User(BaseModel):
    id = Integer(pk=True)
    name = String(length=100)
    email = String(unique=True)

    class Meta:
        table = "users"


class MetaUser(BaseModel):
    user_id = ForeignKey(User)
    description = String()
    image = String()
    date = DateTime(default="CURRENT_TIMESTAMP")


# ---------- Migrations ----------
migrate.collect_models()


# ---------- DB config ----------
DB.connect(
    host="localhost",
    user="root",
    password="root",
    db="test",
    autocommit=False,  # manual transactions
    autoclose=False    # we'll close the pool ourselves at the end
)


# ---------- Test body ----------
async def main():
    await migrate.run()

    conn = await DB.conn()
    try:
        user = await User.create(name="Manual User", email="manual@example.com", _conn=conn)
        meta = await MetaUser.create(user_id=user.id, description="Manual desc", image="manual.jpg", _conn=conn)
        await conn.commit()
        print("✅ Manually committed:", user, meta)
    except Exception as e:
        await conn.rollback()
        print("❌ Rolled back:", e)
    finally:
        await DB.release(conn)
        await DB.close()  # important when autoclose=False


if __name__ == "__main__":
    asyncio.run(main())
