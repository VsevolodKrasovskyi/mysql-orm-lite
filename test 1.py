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
    user_id = ForeignKey(User, on_delete="CASCADE", on_update="CASCADE")
    description = String()
    image = String()
    date = DateTime(default="CURRENT_TIMESTAMP")

    class Meta:
        table = "meta_users"


# ---------- Common DB setup ----------
async def setup_db(autocommit=True, autoclose=True):
    DB.connect(
        host="localhost",
        user="root",
        password="root",
        db="test",
        autocommit=autocommit,
        autoclose=autoclose
    )
    migrate.collect_models()
    await migrate.run()


# ---------- TEST 1 — autocommit=True, autoclose=True ----------
async def test1():
    print("\n=== TEST 1: autocommit=True, autoclose=True ===")
    await setup_db(autocommit=True, autoclose=True)

    await User.delete(id__gte=1)
    await MetaUser.delete(user_id__gte=1)

    u = await User.create(name="Auto", email="auto@example.com")
    await MetaUser.create(user_id=u.id, description="Auto desc", image="auto.jpg")

    user = await User.join(MetaUser, on=[User.id, MetaUser.user_id]).get(id=u.id)
    print(f"Name: {user.name} | Desc: {user.description} | Img: {user.image}")


# ---------- TEST 2 — autocommit=False, autoclose=False ----------
async def test2():
    print("\n=== TEST 2: autocommit=False, autoclose=False ===")
    await setup_db(autocommit=False, autoclose=False)

    conn = await DB.conn()

    try:
        await User.delete(id__gte=1, _conn=conn)
        await MetaUser.delete(user_id__gte=1, _conn=conn)

        u = await User.create(name="Manual", email="manual@example.com", _conn=conn)
        await MetaUser.create(user_id=u.id, description="Manual desc", image="manual.jpg", _conn=conn)

        await conn.commit()
    finally:
        await DB.release(conn)

    user = await User.join(MetaUser, on=[User.id, MetaUser.user_id]).get(name="Manual")
    print(f"Manual commit result: {user.name} | {user.description}")


# ---------- TEST 3 — ROLLBACK on error ----------
async def test3():
    print("\n=== TEST 3: ROLLBACK on error ===")
    await setup_db(autocommit=False, autoclose=False)

    conn = await DB.conn()
    try:
        await User.delete(id__gte=1, _conn=conn)
        await MetaUser.delete(user_id__gte=1, _conn=conn)

        await User.create(name="Rollback", email="rollback@example.com", _conn=conn)
        # This will cause duplicate key error
        await User.create(name="Duplicate", email="rollback@example.com", _conn=conn)
        await conn.commit()
    except Exception as e:
        print(f"Error occurred: {e}, rolling back...")
        await conn.rollback()
    finally:
        await DB.release(conn)
        

    exists = await User.exists(name="Rollback")
    print(f"Rollback applied, record exists? {exists}")
    await DB.close()


# ---------- TEST 4 — Advanced filters & ordering ----------
async def test4():
    print("\n=== TEST 4: Advanced filters & ordering ===")
    await setup_db(autocommit=True, autoclose=True)

    await User.delete(id__gte=1)
    await MetaUser.delete(user_id__gte=1)

    u1 = await User.create(name="User1", email="u1@example.com")
    u2 = await User.create(name="User2", email="u2@example.com")
    u3 = await User.create(name="SpecialUser", email="u3@example.com")

    await MetaUser.create(user_id=u1.id, description="D1", image="i1.jpg")
    await MetaUser.create(user_id=u2.id, description="D2", image="i2.jpg")
    await MetaUser.create(user_id=u3.id, description="Special", image="i3.jpg")

    # LIKE filter
    print("\n-- LIKE filter --")
    like_users = await User.filter(name__like="%User%")
    for u in like_users:
        print(f"{u.id} | {u.name}")

    # IN filter with ordering DESC
    print("\n-- IN filter + ORDER BY DESC --")
    in_users = await User.filter(id__in=[u1.id, u3.id], order_by="-id")
    for u in in_users:
        print(f"{u.id} | {u.name}")

    # JOIN + ORDER BY ASC
    print("\n-- JOIN + ORDER BY ASC --")
    joined = await User.join(MetaUser, on=[User.id, MetaUser.user_id]).all(order_by="name")
    for j in joined:
        print(f"{j.name} | {j.description}")

    # COUNT and EXISTS
    print("\n-- COUNT & EXISTS --")
    print(f"Total users: {await User.count()}")
    print(f"User2 exists? {await User.exists(name='User2')}")

# ---------- Test transaction() ----------
async def test5():
    print("\n=== TEST: transaction() ===")
    await setup_db()

    try:
        async with DB.transaction() as conn:
            await User.create(name="John", email="john@example.com", _conn=conn)
            await User.create(name="Jane", email="jane@example.com", _conn=conn)
            # raise ValueError("Force rollback")
    except ValueError as e:
        print(f"Rollback triggered: {e}")

    exists_after = await User.exists(name="John")
    print(f"Record exists after rollback? {exists_after}")


# ---------- Test session() ----------
async def test6():
    print("\n=== TEST: session() ===")
    await setup_db()

    async with DB.session() as conn:
        await User.create(name="Alice", email="alice@example.com", _conn=conn)
        await conn.commit() 
        await User.create(name="Bob", email="bob@example.com", _conn=conn)
        await conn.commit()

    users = await User.all(order_by="id")
    for u in users:
        print(f"{u.id} | {u.name} | {u.email}")



# ---------- Run all tests ----------
async def main():
    # await test1()
    # await test2()
    # await test3()
    #await test4()
    # await test5()
    await test6()



if __name__ == "__main__":
    asyncio.run(main())
