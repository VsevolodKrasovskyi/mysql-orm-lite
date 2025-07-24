class Field:
    def __init__(self, sql_type, pk=False, unique=False, nullable=False, default=None):
        self.sql_type = sql_type
        self.primary_key = pk
        self.unique = unique
        self.nullable = nullable
        self.default = default

    def ddl(self, name):
        parts = [f"`{name}`", self.sql_type]

        if self.primary_key:
            parts.append("PRIMARY KEY")
            if self.sql_type.upper() == "INT" and name.lower() == "id":
                parts.append("AUTO_INCREMENT")

        if self.unique:
            parts.append("UNIQUE")

        if not self.nullable and not self.primary_key:
            parts.append("NOT NULL")

        if self.default is not None:
            parts.append(f"DEFAULT '{self.default}'")

        return " ".join(parts)


class ForeignKey(Field):
    def __init__(self, *args, to=None, to_field="id", **kwargs):
        if args:
            to = args[0]
            if len(args) > 1:
                to_field = args[1]

        if to is None:
            raise ValueError("ForeignKey: 'to' model must be specified.")

        super().__init__("INT", **kwargs)
        self.to_model = to
        self.to_field = to_field

    def ddl(self, name):
        return Field.ddl(self, name) 

class Integer(Field):
    def __init__(self, **kwargs):
        super().__init__("INT", **kwargs)

class String(Field):
    def __init__(self, length=255, **kwargs):
        super().__init__(f"VARCHAR({length})", **kwargs)


class Boolean(Field):
    def __init__(self, **kwargs):
        super().__init__("TINYINT(1)", **kwargs)


class Text(Field):
    def __init__(self, **kwargs):
        super().__init__("TEXT", **kwargs)


class DateTime(Field):
    def __init__(self, **kwargs):
        super().__init__("DATETIME", **kwargs)


class Float(Field):
    def __init__(self, **kwargs):
        super().__init__("FLOAT", **kwargs)


class Decimal(Field):
    def __init__(self, precision=10, scale=2, **kwargs):
        super().__init__(f"DECIMAL({precision},{scale})", **kwargs)
