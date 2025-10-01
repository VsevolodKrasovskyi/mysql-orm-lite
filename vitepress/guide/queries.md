
# Queries

## Create
```python
u = await User.create(username="alice")
```

## Read
```python
users = await User.all(order_by="-id")
active = await User.filter(is_active=1, age__gte=18)
one = await User.get(id=1)
maybe = await User.get_or_none(email="a@b.com")
```

## Update
```python
await User.update(filters={"id": 1}, updates={"name": "Bob"})
```

## Delete
```python
await User.delete(id=1)
```

## Count / Exists
```python
n = await User.count(is_active=1)
exists = await User.exists(email="alice@example.com")
```

## Joins
```python
Joined = User.join(Profile, on=[User.id, Profile.user_id])
rows = await Joined.all()
```
