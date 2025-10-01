class Field:
    """
    Base field definition for ORM models.
    Stores SQL type and common column constraints (PK, unique, nullable, default).

    Args:
        sql_type (str): MySQL column type, e.g., "INT", "VARCHAR(255)"
        pk (bool): whether this column is a PRIMARY KEY
        unique (bool): whether to add UNIQUE constraint
        nullable (bool): whether NULL is allowed
        default: default value (will be inserted as DEFAULT 'value')

    Usage:
        id = Field("INT", pk=True)
        name = Field("VARCHAR(100)", unique=True, nullable=True)

    Usually, you don't use Field directly — instead, you use subclasses like Integer, String, etc.
    """

    def __init__(self, sql_type, pk=False, unique=False, nullable=True, default=None):
        self.sql_type = sql_type
        self.primary_key = pk
        self.unique = unique
        self.nullable = nullable
        self.default = default

    def ddl(self, name):
        """
        Generate the SQL column definition (part of CREATE TABLE).

        Args:
            name (str): column name

        Returns:
            str: e.g., "`id` INT PRIMARY KEY AUTO_INCREMENT"

        Example:
            Field("INT", pk=True).ddl("id") -> "`id` INT PRIMARY KEY AUTO_INCREMENT"
        """
        parts = [f"`{name}`", self.sql_type]

        if self.primary_key:
            parts.append("PRIMARY KEY")
            # Auto increment if INT primary key named 'id'
            if self.sql_type.upper() == "INT" and name.lower() == "id":
                parts.append("AUTO_INCREMENT")

        if self.unique:
            parts.append("UNIQUE")

        if not self.nullable and not self.primary_key:
            parts.append("NOT NULL")

        if self.default is not None:
            upper_type = self.sql_type.upper()
            if (
                isinstance(self.default, str)
                and self.default.upper() in ("CURRENT_TIMESTAMP", "NOW()")
                and upper_type in ("DATETIME", "TIMESTAMP")
            ):
                parts.append(f"DEFAULT {self.default}")
            else:
                parts.append(f"DEFAULT '{self.default}'")


        return " ".join(parts)


class ForeignKey(Field):
    """
    Field type for defining a foreign key relation.

    Args:
        to (BaseModel subclass): model class being referenced
        to_field (str): name of the column in the referenced table (default "id")
        kwargs: passed to Field (e.g., pk, unique, nullable, default)

    Example:
        user_id = ForeignKey(User, to_field="id", nullable=False)

    Note:
        - This class inherits from Field and sets SQL type to "INT" by default.
        - DDL will be generated, and the BaseModel.generate_create_table method
          will add the FOREIGN KEY constraint automatically.
    """
    def __init__(self, *args, to=None, to_field="id",
                 on_delete=None, on_update=None, sql_type=None, **kwargs):
        if args:
            to = args[0]
            if len(args) > 1:
                to_field = args[1]
        if to is None:
            raise ValueError("ForeignKey: 'to' model must be specified.")

        if sql_type is None:
            try:
                ref_field = to.__fields__[to_field]
                sql_type = ref_field.sql_type
            except Exception:
                sql_type = "INT"  # fallback

        super().__init__(sql_type, **kwargs)
        self.to_model = to
        self.to_field = to_field
        self.on_delete = on_delete
        self.on_update = on_update

    def ddl(self, name):
        return Field.ddl(self, name)

class Integer(Field):
    """
    Shortcut for an INT column.

    Example:
        id = Integer(pk=True)
        age = Integer(nullable=True, default=18)
    """
    def __init__(self, **kwargs):
        super().__init__("INT", **kwargs)


class String(Field):
    """
    Shortcut for a VARCHAR column.

    Args:
        length (int): max string length (default 255)

    Example:
        name = String(length=100, unique=True)
    """
    def __init__(self, length=255, **kwargs):
        super().__init__(f"VARCHAR({length})", **kwargs)


class Boolean(Field):
    """
    Shortcut for a boolean column (TINYINT(1)).

    Example:
        is_active = Boolean(default=1)
    """
    def __init__(self, **kwargs):
        super().__init__("TINYINT(1)", **kwargs)


class Text(Field):
    """
    Shortcut for a TEXT column (unbounded length).

    Example:
        bio = Text(nullable=True)
    """
    def __init__(self, **kwargs):
        super().__init__("TEXT", **kwargs)


class DateTime(Field):
    """
    Shortcut for a DATETIME column.

    Example:
        created_at = DateTime(default="CURRENT_TIMESTAMP")
    """
    def __init__(self, **kwargs):
        super().__init__("DATETIME", **kwargs)


class Date(Field):
    """
    Shortcut for a DATE column.

    Example:
        created_at = Date(default="CURRENT_TIMESTAMP")
    """
    def __init__(self, **kwargs):
        super().__init__("DATE", **kwargs)


class Float(Field):
    """
    Shortcut for a FLOAT column.

    Example:
        rating = Float(default=0.0)
    """
    def __init__(self, **kwargs):
        super().__init__("FLOAT", **kwargs)


class Decimal(Field):
    """
    Shortcut for a DECIMAL column.

    Args:
        precision (int): total number of digits
        scale (int): number of digits after decimal point

    Example:
        price = Decimal(precision=8, scale=2, default=0.00)
    """
    def __init__(self, precision=10, scale=2, **kwargs):
        super().__init__(f"DECIMAL({precision},{scale})", **kwargs)

class Set(Field):
    
    def __init__(self, values, **kwargs):
        vals = list(values or [])
        if not vals:
            raise ValueError("Set requires at least one value")
        sql = "SET(" + ",".join("'" + v.replace("'", "''") + "'" for v in vals) + ")"
        super().__init__(sql, **kwargs)

class Enum(Field):
    """
    Shortcut for ENUM column.

    Args:
        values (list[str]): list of allowed values
        kwargs: passed to Field (nullable, default, unique, etc.)

    Example:
        status = Enum(values=["draft", "published", "archived"], default="draft")
    """
    def __init__(self, values, **kwargs):
        vals = list(values or [])
        if not vals:
            raise ValueError("Enum requires at least one value")
        sql = "ENUM(" + ",".join("'" + v.replace("'", "''") + "'" for v in vals) + ")"
        super().__init__(sql, **kwargs)
        self.values = vals


class JSON(Field):
    def __init__(self, **kwargs):
        super().__init__("JSON", **kwargs)

class ManyToMany:
    """
    Declarative marker for a Many-to-Many relation, used **only** inside a model's Meta.

    Usage:
        class User(BaseModel):
            class Meta:
                bonuses = ManyToMany("Bonus", through="UserHasProduct")

    What it does:
      - The attribute name on Meta (e.g. `bonuses`) defines two reserved properties on the owner model:
            owner.bonuses       -> awaitable manager returning target objects (e.g. Bonus[])
            owner.bonuses_rel   -> awaitable list of through rows with attached target (rel.bonus)
      - Resolution is lazy: target/through models and FK column names are resolved on first access.
      - No joins are required in user code; the ORM performs batched IN-queries under the hood.

    Notes:
      - `through` must be an explicit model with two ForeignKey fields pointing to owner and target.
      - To get the reverse side, declare a symmetric ManyToMany on the other model (e.g. `users = ManyToMany("User", through="UserHasProduct")`).
      - The generated property names (e.g. `bonuses`, `bonuses_rel`) are reserved and cannot be redefined on the model.
    """
    def __init__(self, target_model, through):
        self.target_model = target_model   # class or string
        self.through = through             # class or string

    def __repr__(self):
        return f"<ManyToMany target={self.target_model} through={self.through}>"