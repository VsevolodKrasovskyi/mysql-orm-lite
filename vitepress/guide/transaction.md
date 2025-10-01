
# Transaction

ACID transaction (BEGIN/COMMIT/ROLLBACK).

```python
async with DB.transaction() as conn:
    a = await Account.get(id=1, _conn=conn)
    b = await Account.get(id=2, _conn=conn)
    if a.balance < 100:
        raise ValueError("insufficient funds")
    await Account.update(filters={"id": a.id}, updates={"balance": a.balance - 100}, _conn=conn)
    await Account.update(filters={"id": b.id}, updates={"balance": b.balance + 100}, _conn=conn)
```
