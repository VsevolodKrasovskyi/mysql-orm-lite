"""
TEST 3 - ROLLBACK on error (autocommit=False, autoclose=False)
In one transaction create a user and a bit meta (description=None),
expect IntegrityError and rollback the whole transaction.
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
    description = String()   # NOT NULL by default -> None will cause an error
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
    autocommit=False,
    autoclose=False
)


# ---------- Test body ----------
async def main():
    await migrate.run()

    conn = await DB.conn()
    try:
        user = await User.create(name="Broken", email="broken@example.com", _conn=conn)
        # Error: description=None with NOT NULL field
        await MetaUser.create(user_id=user.id, description=None, image="broken.jpg", _conn=conn)
        await conn.commit()
        print("⚠️ Unexpected: commit passed (should fail)")
    except Exception as e:
        await conn.rollback()
        print("✅ Rolled back transaction:", e)
    finally:
        await DB.release(conn)
        await DB.close()

    # Let's make sure Broken doesn't commit.
    exists = await User.exists(email="broken@example.com")
    print("Should be False, exists:", exists)


if __name__ == "__main__":
    asyncio.run(main())
