"""
TEST 1 - autocommit=True, autoclose=True
Let's check that INSERTs are committed without manual commit(),
and the connection pool is closed automatically on exit.
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
    autocommit=True,   # server autocommit
    autoclose=True     # autoclosing the pool on exit
)


# ---------- Test body ----------
async def main():
    await migrate.run()

    user = await User.get_or_create(name="Auto User", email="auto@example.com")
    meta = await MetaUser.get_or_create(user_id=user[0].id, description="Auto desc", image="auto.jpg")

    print("✅ Created:", user, meta)

    # sanity-check
    fetched = await User.get_or_create(email="auto@example.com")
    print("Fetched:", fetched)


if __name__ == "__main__":
    asyncio.run(main())
