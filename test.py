from mysql_orm.base import BaseModel, DB
from mysql_orm.fields import String, Integer, ForeignKey, DateTime
from mysql_orm import migrate
import asyncio


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
    date =DateTime(default="CURRENT_TIMESTAMP")

migrate.collect_models()

DB.connect(
        host="localhost",
        user="root",
        password="root",
        db="test",
        autocommit=True
    )


async def main():
    await migrate.run()
    all_users = await User.all()
    for u in all_users:
        meta = await MetaUser.get(user_id=u.id)
       # print(f"{u.name} - {meta.description}")

    print(all_users)

asyncio.run(main())