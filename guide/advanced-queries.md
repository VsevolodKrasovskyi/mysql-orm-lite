
# Advanced Queries

Operators supported in filters:
- `field=value`
- `field__gte=value`
- `field__lte=value`
- `field__like="prefix%"`
- `field__in=[1,2,3]`

```python
users = await User.filter(age__gte=18, username__like="A%")
```
