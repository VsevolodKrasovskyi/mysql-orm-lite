class _AwaitableList:
    def __init__(self, coro):
        self._coro = coro
    def __await__(self):
        return self._coro.__await__()


class ManyToManyManager:
    def __init__(self, owner, resolve_callable):
        self._owner = owner
        self._resolve = resolve_callable 

    def __await__(self):
        return self.all().__await__()

    async def all(self):
        target, through, self_fk, target_fk, target_attr = self._resolve()
        rel_rows = await through.filter(**{self_fk: getattr(self._owner, 'id')})
        if not rel_rows:
            return []
        ids = [getattr(r, target_fk) for r in rel_rows]
        ids = list(dict.fromkeys(ids))  # preserve order, remove dups
        targets = await target.filter(id__in=ids)
        tmap = {getattr(t, 'id'): t for t in targets}
        return [tmap[i] for i in ids if i in tmap]

    async def through(self):
        target, through, self_fk, target_fk, target_attr = self._resolve()
        rel_rows = await through.filter(**{self_fk: getattr(self._owner, 'id')})
        if not rel_rows:
            return []
        ids = [getattr(r, target_fk) for r in rel_rows]
        targets = await target.filter(id__in=ids)
        tmap = {getattr(t, 'id'): t for t in targets}
        for r in rel_rows:
            setattr(r, target_attr, tmap.get(getattr(r, target_fk)))
        return rel_rows

    async def add(self, target_obj, **through_fields):
        target, through, self_fk, target_fk, target_attr = self._resolve()
        await through.create(**{
            self_fk: getattr(self._owner, 'id'),
            target_fk: getattr(target_obj, 'id'),
            **through_fields
        })

    async def remove(self, target_obj):
        target, through, self_fk, target_fk, target_attr = self._resolve()
        await through.delete(**{
            self_fk: getattr(self._owner, 'id'),
            target_fk: getattr(target_obj, 'id'),
        })

    async def clear(self):
        target, through, self_fk, target_fk, target_attr = self._resolve()
        await through.delete(**{self_fk: getattr(self._owner, 'id')})