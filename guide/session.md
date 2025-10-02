
# Session

Use one pooled connection without ACID guarantees.

```python
async with DB.session() as conn:
    u = await User.create(username="alice", _conn=conn)
    again = await User.get(id=u.id, _conn=conn)
```
