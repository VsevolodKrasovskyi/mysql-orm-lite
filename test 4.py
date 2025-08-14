"""
TEST 4 — Advanced filters & ordering
Checking order_by, __like, __in, count(), exists().
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
    autocommit=True,
    autoclose=True
)


# ---------- Test body ----------
async def main():
    await migrate.run()

    # Data preparation (idempotent - get_or_create)
    await User.get_or_create(name="Alice Filter", email="alice.filter@example.com")
    await User.get_or_create(name="Bob Filter",   email="bob.filter@example.com")
    await User.get_or_create(name="Carol Filter", email="carol.filter@example.com")

    print("== Users LIKE '%Filter%' ordered by -id ==")
    users = await User.filter(name__like="%Filter%", order_by="-id")
    for u in users:
        print(u)

    print("== Users with id IN (...) ==")
    ids = [u.id for u in users[:2]]
    subset = await User.filter(id__in=ids, order_by="id")
    for u in subset:
        print(u)

    total = await User.count()
    print("Total users:", total)

    print("Exists bob.filter@example.com ? =>", await User.exists(email="bob.filter@example.com"))
    print("Exists ghost@example.com ?      =>", await User.exists(email="ghost@example.com"))


if __name__ == "__main__":
    asyncio.run(main())
