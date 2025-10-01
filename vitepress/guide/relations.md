
# Relations

## ForeignKey
```python
class Profile(BaseModel):
    id = Integer(pk=True)
    user_id = ForeignKey(User, on_delete="CASCADE")
```

## ManyToMany
```python
class User(BaseModel):
    id = Integer(pk=True)
    class Meta:
        bonuses = ManyToMany("Bonus", through="UserBonus")
```

Usage:
```python
u = await User.get(id=1)
bonuses = await u.bonuses
rels = await u.bonuses_rel
await u.bonuses.add(bonus_obj, extra_field=123)
await u.bonuses.remove(bonus_obj)
await u.bonuses.clear()
```
