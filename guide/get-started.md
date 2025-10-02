# Get Started

`ormysql` is a tiny async ORM built on top of **aiomysql**.  
It focuses on simplicity and performance while keeping the API minimal and predictable.

## Installation

```bash
pip install ormysql

```

## Quick Example
Below is a minimal example showing how to define a model, connect to the database, run migrations, and perform basic CRUD operations.

```python
import asyncio
from ormysql.base import BaseModel
from ormysql.db import DB
from ormysql import migrate
from ormysql.fields import Integer, String

# 1. Define your model
class User(BaseModel):
    id = Integer(pk=True)
    name = String(length=100)

async def connector():
    DB.connect(
        host="127.0.0.1",
        user="root",
        password="root",
        db="test",
        autocommit=True
    )
    migrate.collect_models()
    await migrate.run()

# 4. Use your model
async def main():
    await connector()
    user = await User.create(name="Alice")

    # Read
    fetched = await User.get_or_none(id=user.id)
    print("Fetched:", fetched)

    # Update
    await User.update({"id": user.id}, {"name": "Alice Updated"})

    # Delete
    await User.delete(id=user.id)

if __name__ == "__main__":
    asyncio.run(main())
```