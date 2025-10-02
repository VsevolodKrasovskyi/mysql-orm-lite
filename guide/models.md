
# Models

Models inherit from `BaseModel`. Each attribute is a Field.

```python
class User(BaseModel):
    id = Integer(pk=True)
    username = String(length=50, unique=True)
    is_active = Boolean(default=1)
```

### Meta
- `table` – override table name
- `ManyToMany` – declare M2M relation inside `Meta`

### Utils
- `to_dict()`
- `__repr__`
