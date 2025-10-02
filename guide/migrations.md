
# Migrations

The ORM generates `CREATE TABLE IF NOT EXISTS`.

## register()
```python
from ormysql.migrate import register, run
register(User, Profile)
await run()
```

## collect_models()
```python
from ormysql.migrate import collect_models, run
collect_models()
await run()
```
