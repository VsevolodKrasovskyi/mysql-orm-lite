from mysql_orm.base import BaseModel, DB
from mysql_orm.fields import String, Integer, Text, ForeignKey
from mysql_orm import migrate
import asyncio


class User(BaseModel):
    id = Integer(pk=True)
    name = String(length=100)
    email = String(unique=True)
    bio = Text(nullable=True)

    class Meta:
        table = "users"

class MetaUser(BaseModel):
    user_id = ForeignKey(User)
    description = String()
    image = String()
migrate.collect_models()

DB.connect(
        host="localhost",
        user="root",
        password="root",
        db="test",
        autocommit=True
    )

async def main():
    users = await User.all()
    meta = await MetaUser.all()

    for user in users:
        print(f"User: {user.name}")
asyncio.run(main())