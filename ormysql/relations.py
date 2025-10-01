# ormysql/relations.py

class _AwaitableList:
    def __init__(self, coro):
        self._coro = coro
    def __await__(self):
        return self._coro.__await__()


class ManyToManyManager:
    def __init__(self, owner, resolve_callable):
        self._owner = owner
        self._resolve = resolve_callable

    # ---- helpers ----
    @staticmethod
    def _pk_name(model_cls):
        # найти имя PK по объявленным полям
        for fname, fobj in getattr(model_cls, "__fields__", {}).items():
            if getattr(fobj, "primary_key", False):
                return fname
        return "id"  # запасной вариант

    def __await__(self):
        return self.all().__await__()

    async def all(self):
        target, through, self_fk, target_fk, target_attr = self._resolve()
        owner_pk = self._pk_name(self._owner.__class__)
        target_pk = self._pk_name(target)

        # все строки в through для данного owner
        rel_rows = await through.filter(**{self_fk: getattr(self._owner, owner_pk)})
        if not rel_rows:
            return []

        ids = [getattr(r, target_fk) for r in rel_rows]
        ids = list(dict.fromkeys(ids))  # preserve order, dedup

        # подтащим таргеты пачкой
        targets = await target.filter(**{f"{target_pk}__in": ids})
        tmap = {getattr(t, target_pk): t for t in targets}
        return [tmap[i] for i in ids if i in tmap]

    async def through(self):
        target, through, self_fk, target_fk, target_attr = self._resolve()
        owner_pk = self._pk_name(self._owner.__class__)
        target_pk = self._pk_name(target)

        rel_rows = await through.filter(**{self_fk: getattr(self._owner, owner_pk)})
        if not rel_rows:
            return []

        ids = [getattr(r, target_fk) for r in rel_rows]
        targets = await target.filter(**{f"{target_pk}__in": ids})
        tmap = {getattr(t, target_pk): t for t in targets}

        # пришиваем объект таргета к каждой through-строке
        for r in rel_rows:
            setattr(r, target_attr, tmap.get(getattr(r, target_fk)))
        return rel_rows

    async def add(self, target_obj, **through_fields):
        target, through, self_fk, target_fk, _ = self._resolve()
        owner_pk = self._pk_name(self._owner.__class__)
        target_pk = self._pk_name(target)
        await through.create(**{
            self_fk: getattr(self._owner, owner_pk),
            target_fk: getattr(target_obj, target_pk),
            **through_fields
        })

    async def remove(self, target_obj):
        target, through, self_fk, target_fk, _ = self._resolve()
        owner_pk = self._pk_name(self._owner.__class__)
        target_pk = self._pk_name(target)
        await through.delete(**{
            self_fk: getattr(self._owner, owner_pk),
            target_fk: getattr(target_obj, target_pk),
        })

    async def clear(self):
        _, through, self_fk, _, _ = self._resolve()
        owner_pk = self._pk_name(self._owner.__class__)
        await through.delete(**{self_fk: getattr(self._owner, owner_pk)})
