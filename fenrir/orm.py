"""
fenrir.orm — Lightweight async ORM for Fenrir.

A minimal, high-performance ORM that supports SQLite (via aiosqlite)
and PostgreSQL (via asyncpg). Designed for simplicity and speed.

Usage::

    from fenrir.orm import Database, Model, fields

    # Configure database
    db = Database("sqlite:///app.db")
    # or: db = Database("postgresql://user:pass@localhost/db")

    # Define models
    class User(Model):
        __tablename__ = "users"

        id = fields.Integer(primary_key=True)
        name = fields.String(max_length=100)
        email = fields.String(max_length=255, unique=True)
        age = fields.Integer(default=0)
        created_at = fields.Datetime(auto_now_add=True)

    # Create tables
    await db.create_all()

    # CRUD operations
    user = await User.create(name="Alice", email="alice@example.com")
    user = await User.get(id=1)
    users = await User.filter(age__gte=18)
    await user.update(name="Alice Smith")
    await user.delete()

    # Raw queries
    rows = await db.fetch_all("SELECT * FROM users WHERE age > ?", [18])
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from datetime import datetime, timezone
from typing import (
    Any,
    Callable,
    Dict,
    Generator,
    List,
    Optional,
    Sequence,
    Tuple,
    Type,
    Union,
)

from fenrir.json import _orjson, _HAS_ORJSON

logger = logging.getLogger("fenrir.orm")


# ═══════════════════════════════════════════════════════════════════════
# Field types
# ═══════════════════════════════════════════════════════════════════════

class Field:
    """Base field class."""

    def __init__(
        self,
        primary_key: bool = False,
        default: Any = None,
        null: bool = True,
        unique: bool = False,
        index: bool = False,
        column_name: Optional[str] = None,
    ) -> None:
        self.primary_key = primary_key
        self.default = default
        self.null = null
        self.unique = unique
        self.index = index
        self.column_name = column_name
        self.name = ""
        self.model_class: Optional[type] = None

    def contribute_to_class(self, model_class: type, name: str) -> None:
        self.name = name
        self.model_class = model_class
        if not self.column_name:
            self.column_name = name

    def get_column_type(self, dialect: str = "sqlite") -> str:
        raise NotImplementedError

    def to_python(self, value: Any) -> Any:
        if value is None:
            return None
        return value

    def to_db(self, value: Any) -> Any:
        if value is None:
            return None
        return value

    def sql_default(self) -> str:
        if self.default is not None:
            if callable(self.default):
                return ""
            return f" DEFAULT {self._sql_literal(self.default)}"
        if self.null:
            return ""
        return ""

    def _sql_literal(self, value: Any) -> str:
        if value is None:
            return "NULL"
        if isinstance(value, bool):
            return "1" if value else "0"
        if isinstance(value, (int, float)):
            return str(value)
        if isinstance(value, str):
            escaped = value.replace("'", "''")
            return f"'{escaped}'"
        return f"'{str(value)}'"


class Integer(Field):
    def __init__(self, primary_key: bool = False, default: Any = None, **kwargs) -> None:
        super().__init__(primary_key=primary_key, default=default, null=False, **kwargs)

    def get_column_type(self, dialect: str = "sqlite") -> str:
        if self.primary_key:
            if dialect == "postgresql":
                return "SERIAL PRIMARY KEY"
            return "INTEGER PRIMARY KEY AUTOINCREMENT"
        return "INTEGER"

    def to_python(self, value: Any) -> Any:
        if value is None:
            return None
        try:
            return int(value)
        except (ValueError, TypeError):
            return None


class String(Field):
    def __init__(self, max_length: int = 255, **kwargs) -> None:
        super().__init__(**kwargs)
        self.max_length = max_length

    def get_column_type(self, dialect: str = "sqlite") -> str:
        return f"VARCHAR({self.max_length})"

    def to_python(self, value: Any) -> Any:
        if value is None:
            return None
        return str(value)


class Text(Field):
    def get_column_type(self, dialect: str = "sqlite") -> str:
        return "TEXT"


class Float(Field):
    def __init__(self, default: Any = 0.0, **kwargs) -> None:
        super().__init__(default=default, **kwargs)

    def get_column_type(self, dialect: str = "sqlite") -> str:
        return "REAL"

    def to_python(self, value: Any) -> Any:
        if value is None:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None


class Boolean(Field):
    def __init__(self, default: bool = False, **kwargs) -> None:
        super().__init__(default=default, **kwargs)

    def get_column_type(self, dialect: str = "sqlite") -> str:
        return "INTEGER"

    def to_python(self, value: Any) -> Any:
        if value is None:
            return None
        return bool(value)

    def to_db(self, value: Any) -> Any:
        if value is None:
            return None
        return 1 if value else 0


class Datetime(Field):
    def __init__(self, auto_now: bool = False, auto_now_add: bool = False, **kwargs) -> None:
        super().__init__(**kwargs)
        self.auto_now = auto_now
        self.auto_now_add = auto_now_add

    def get_column_type(self, dialect: str = "sqlite") -> str:
        return "TEXT"

    def to_python(self, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                return None
        return None

    def to_db(self, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.isoformat()
        return str(value)


class JSONField(Field):
    def get_column_type(self, dialect: str = "sqlite") -> str:
        return "TEXT"

    def to_python(self, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, (dict, list)):
            return value
        if isinstance(value, str):
            try:
                if _HAS_ORJSON:
                    return _orjson.loads(value)
                return json.loads(value)
            except Exception:
                return None
        return value

    def to_db(self, value: Any) -> Any:
        if value is None:
            return None
        try:
            if _HAS_ORJSON:
                result = _orjson.dumps(value)
                return result.decode("utf-8") if isinstance(result, bytes) else result
            return json.dumps(value)
        except (TypeError, ValueError) as e:
            raise ValueError(f"Cannot serialize to JSON: {e}") from e


# ═══════════════════════════════════════════════════════════════════════
# Query builder
# ═══════════════════════════════════════════════════════════════════════

# Operator inversion map for exclude()
_OPERATOR_INVERT = {
    "eq": "neq",
    "neq": "eq",
    "gt": "lte",
    "gte": "lt",
    "lt": "gte",
    "lte": "gt",
    "contains": "not_contains",
    "startswith": "not_startswith",
    "endswith": "not_endswith",
    "in": "not_in",
    "isnull": "not_isnull",
}


class QuerySet:
    """Lazy query builder for Model operations."""

    def __init__(self, model_class: type, db: "Database") -> None:
        self.model_class = model_class
        self.db = db
        self._filters: List[Tuple[str, str, Any]] = []
        self._order: List[str] = []
        self._limit: Optional[int] = None
        self._offset: Optional[int] = None

    def _clone(self) -> "QuerySet":
        qs = QuerySet(self.model_class, self.db)
        qs._filters = list(self._filters)
        qs._order = list(self._order)
        qs._limit = self._limit
        qs._offset = self._offset
        return qs

    def filter(self, **kwargs: Any) -> "QuerySet":
        qs = self._clone()
        for key, value in kwargs.items():
            if "__" in key:
                field_name, op = key.rsplit("__", 1)
            else:
                field_name, op = key, "eq"
            qs._filters.append((field_name, op, value))
        return qs

    def exclude(self, **kwargs: Any) -> "QuerySet":
        qs = self._clone()
        for key, value in kwargs.items():
            if "__" in key:
                field_name, op = key.rsplit("__", 1)
            else:
                field_name, op = key, "eq"
            # Invert the operator
            op = _OPERATOR_INVERT.get(op, f"not_{op}")
            qs._filters.append((field_name, op, value))
        return qs

    def order_by(self, *fields: str) -> "QuerySet":
        qs = self._clone()
        qs._order = list(fields)
        return qs

    def limit(self, n: int) -> "QuerySet":
        qs = self._clone()
        qs._limit = n
        return qs

    def offset(self, n: int) -> "QuerySet":
        qs = self._clone()
        qs._offset = n
        return qs

    @staticmethod
    def _escape_like(value: str) -> str:
        """Escape LIKE wildcards in value."""
        return value.replace("%", "\\%").replace("_", "\\_")

    def _build_where(self) -> Tuple[str, List[Any]]:
        if not self._filters:
            return "", []

        clauses = []
        params = []
        model_fields = {f.name: f for f in self.model_class._meta["fields"].values()}

        for field_name, op, value in self._filters:
            col = model_fields.get(field_name, Field(column_name=field_name)).column_name or field_name

            if op == "eq":
                clauses.append(f"{col} = ?")
                params.append(value)
            elif op == "neq":
                clauses.append(f"{col} != ?")
                params.append(value)
            elif op == "gt":
                clauses.append(f"{col} > ?")
                params.append(value)
            elif op == "gte":
                clauses.append(f"{col} >= ?")
                params.append(value)
            elif op == "lt":
                clauses.append(f"{col} < ?")
                params.append(value)
            elif op == "lte":
                clauses.append(f"{col} <= ?")
                params.append(value)
            elif op == "contains":
                clauses.append(f"{col} LIKE ? ESCAPE '\\'")
                params.append(f"%{self._escape_like(str(value))}%")
            elif op == "startswith":
                clauses.append(f"{col} LIKE ? ESCAPE '\\'")
                params.append(f"{self._escape_like(str(value))}%")
            elif op == "endswith":
                clauses.append(f"{col} LIKE ? ESCAPE '\\'")
                params.append(f"%{self._escape_like(str(value))}")
            elif op == "not_contains":
                clauses.append(f"{col} NOT LIKE ? ESCAPE '\\'")
                params.append(f"%{self._escape_like(str(value))}%")
            elif op == "not_startswith":
                clauses.append(f"{col} NOT LIKE ? ESCAPE '\\'")
                params.append(f"{self._escape_like(str(value))}%")
            elif op == "not_endswith":
                clauses.append(f"{col} NOT LIKE ? ESCAPE '\\'")
                params.append(f"%{self._escape_like(str(value))}")
            elif op == "in":
                if not value:
                    clauses.append("0")  # Empty IN — always false
                else:
                    placeholders = ", ".join("?" * len(value))
                    clauses.append(f"{col} IN ({placeholders})")
                    params.extend(value)
            elif op == "not_in":
                if not value:
                    pass  # Empty NOT IN — always true
                else:
                    placeholders = ", ".join("?" * len(value))
                    clauses.append(f"{col} NOT IN ({placeholders})")
                    params.extend(value)
            elif op == "isnull":
                if value:
                    clauses.append(f"{col} IS NULL")
                else:
                    clauses.append(f"{col} IS NOT NULL")
            elif op == "not_isnull":
                if value:
                    clauses.append(f"{col} IS NOT NULL")
                else:
                    clauses.append(f"{col} IS NULL")

        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        return where, params

    def _build_order(self) -> str:
        if not self._order:
            return ""
        # Validate field names to prevent injection
        valid_fields = set(self.model_class._meta["fields"].keys())
        parts = []
        for field in self._order:
            if field.startswith("-"):
                fname = field[1:]
            else:
                fname = field
            if fname in valid_fields:
                if field.startswith("-"):
                    parts.append(f"{fname} DESC")
                else:
                    parts.append(f"{fname} ASC")
        if not parts:
            return ""
        return " ORDER BY " + ", ".join(parts)

    async def _fetch_all(self) -> List[Any]:
        table = self.model_class._meta["tablename"]
        where, params = self._build_where()
        order = self._build_order()
        sql = f"SELECT * FROM {table}{where}{order}"

        if self._limit is not None:
            sql += f" LIMIT {int(self._limit)}"
        if self._offset is not None:
            sql += f" OFFSET {int(self._offset)}"

        rows = await self.db.fetch_all(sql, params)
        return [self.model_class._from_row(row) for row in rows]

    async def _fetch_one(self) -> Optional[Any]:
        table = self.model_class._meta["tablename"]
        where, params = self._build_where()
        order = self._build_order()
        sql = f"SELECT * FROM {table}{where}{order} LIMIT 1"
        row = await self.db.fetch_one(sql, params)
        if row:
            return self.model_class._from_row(row)
        return None

    async def _count(self) -> int:
        table = self.model_class._meta["tablename"]
        where, params = self._build_where()
        sql = f"SELECT COUNT(*) as cnt FROM {table}{where}"
        row = await self.db.fetch_one(sql, params)
        return row["cnt"] if row else 0

    async def _exists(self) -> bool:
        count = await self._count()
        return count > 0

    def __await__(self) -> Generator[Any, None, List[Any]]:
        return self._fetch_all().__await__()

    async def all(self) -> List[Any]:
        return await self._fetch_all()

    async def first(self) -> Optional[Any]:
        return await self._fetch_one()

    async def count(self) -> int:
        return await self._count()

    async def exists(self) -> bool:
        return await self._exists()

    async def delete(self) -> int:
        table = self.model_class._meta["tablename"]
        where, params = self._build_where()
        sql = f"DELETE FROM {table}{where}"
        result = await self.db.execute(sql, params)
        return result

    async def update(self, **kwargs: Any) -> int:
        table = self.model_class._meta["tablename"]
        where, params = self._build_where()
        set_parts = []
        set_values = []
        valid_fields = set(self.model_class._meta["fields"].keys())
        for field_name, value in kwargs.items():
            if field_name not in valid_fields:
                raise ValueError(f"Invalid field name: {field_name}")
            field_obj = self.model_class._meta["fields"].get(field_name)
            if field_obj:
                value = field_obj.to_db(value)
            set_parts.append(f"{field_name} = ?")
            set_values.append(value)
        sql = f"UPDATE {table} SET {', '.join(set_parts)}{where}"
        result = await self.db.execute(sql, set_values + params)
        return result


# ═══════════════════════════════════════════════════════════════════════
# Model metaclass and base
# ═══════════════════════════════════════════════════════════════════════

class ModelMeta(type):
    """Metaclass for Model that collects fields."""

    def __new__(mcs, name: str, bases: tuple, namespace: dict) -> "ModelMeta":
        if name == "Model":
            return super().__new__(mcs, name, bases, namespace)

        fields_dict = {}
        primary_key = None

        # Collect fields from bases
        for base in bases:
            if hasattr(base, "_meta") and base._meta:
                for fname, field in base._meta["fields"].items():
                    fields_dict[fname] = field
                    if field.primary_key:
                        primary_key = fname

        # Collect fields from current class
        for key, value in list(namespace.items()):
            if isinstance(value, Field):
                fields_dict[key] = value
                namespace.pop(key)
                if value.primary_key:
                    primary_key = key

        # Default primary key if none defined
        if primary_key is None and "id" not in fields_dict:
            pk = Integer(primary_key=True)
            pk.contribute_to_class(None, "id")
            fields_dict["id"] = pk
            primary_key = "id"

        tablename = namespace.get("__tablename__", name.lower() + "s")

        meta = {
            "tablename": tablename,
            "fields": fields_dict,
            "primary_key": primary_key,
        }

        namespace["_meta"] = meta
        cls = super().__new__(mcs, name, bases, namespace)

        # Register fields with class
        for fname, field in fields_dict.items():
            if field.model_class is None:
                field.contribute_to_class(cls, fname)

        return cls


class Model(metaclass=ModelMeta):
    """Base model class for ORM.

    Usage::

        class User(Model):
            __tablename__ = "users"

            id = fields.Integer(primary_key=True)
            name = fields.String(max_length=100)
    """

    _meta: Dict[str, Any] = {"fields": {}, "tablename": "", "primary_key": None}
    _db: Optional["Database"] = None

    def __init__(self, **kwargs: Any) -> None:
        meta = self._meta
        for fname, field in meta["fields"].items():
            if fname in kwargs:
                value = kwargs[fname]
            elif field.primary_key:
                value = None
            elif field.default is not None:
                value = field.default() if callable(field.default) else field.default
            else:
                value = None
            setattr(self, fname, value)

        # Warn about unknown kwargs
        for key, value in kwargs.items():
            if key not in meta["fields"]:
                logger.debug("Setting unknown attribute '%s' on %s", key, type(self).__name__)
                setattr(self, key, value)

    @classmethod
    def _from_row(cls, row: Any) -> "Model":
        """Create a model instance from a database row."""
        data = {}
        for fname, field in cls._meta["fields"].items():
            if isinstance(row, dict):
                raw = row.get(fname)
            elif hasattr(row, fname):
                raw = getattr(row, fname, None)
            elif isinstance(row, (tuple, list)) and fname in cls._meta["fields"]:
                # Try by index
                idx = list(cls._meta["fields"].keys()).index(fname)
                raw = row[idx] if idx < len(row) else None
            else:
                raw = None
            data[fname] = field.to_python(raw)
        return cls(**data)

    def to_dict(self) -> Dict[str, Any]:
        result = {}
        for fname in self._meta["fields"]:
            value = getattr(self, fname, None)
            if isinstance(value, datetime):
                value = value.isoformat()
            elif hasattr(value, "isoformat"):
                value = value.isoformat()
            result[fname] = value
        return result

    async def save(self) -> None:
        """Insert or update this instance."""
        if self._db is None:
            raise RuntimeError("Model not bound to a database. Use Model.bind(db) first.")

        pk_field = self._meta["primary_key"]
        pk_value = getattr(self, pk_field, None)

        if pk_value is None:
            await self._insert()
        else:
            await self._update()

    async def _insert(self) -> None:
        meta = self._meta
        fields_list = []
        values = []
        placeholders = []

        for fname, field in meta["fields"].items():
            if field.primary_key and getattr(self, fname) is None:
                continue
            value = getattr(self, fname, None)
            if hasattr(field, "auto_now_add") and field.auto_now_add and value is None:
                value = datetime.now(timezone.utc)
                setattr(self, fname, value)
            fields_list.append(fname)
            values.append(field.to_db(value))
            placeholders.append("?")

        table = meta["tablename"]
        sql = f"INSERT INTO {table} ({', '.join(fields_list)}) VALUES ({', '.join(placeholders)})"
        cursor = await self._db.execute(sql, values)

        if meta["primary_key"] and getattr(self, meta["primary_key"]) is None:
            if self._db._dialect == "sqlite":
                setattr(self, meta["primary_key"], cursor)
            else:
                # PostgreSQL: fetch the inserted ID via RETURNING
                pk_col = meta["primary_key"]
                pk_val = getattr(self, meta["primary_key"])
                if pk_val is None:
                    # Try to get the last inserted row
                    try:
                        result = await self._db.fetch_one(
                            f"SELECT {pk_col} FROM {table} ORDER BY {pk_col} DESC LIMIT 1"
                        )
                        if result:
                            setattr(self, meta["primary_key"], result[pk_col])
                    except Exception:
                        pass

    async def _update(self) -> None:
        meta = self._meta
        pk_field = meta["primary_key"]
        pk_value = getattr(self, pk_field)

        set_parts = []
        set_values = []

        for fname, field in meta["fields"].items():
            if fname == pk_field:
                continue
            value = getattr(self, fname, None)
            if hasattr(field, "auto_now") and field.auto_now:
                value = datetime.now(timezone.utc)
                setattr(self, fname, value)
            set_parts.append(f"{fname} = ?")
            set_values.append(field.to_db(value))

        table = meta["tablename"]
        sql = f"UPDATE {table} SET {', '.join(set_parts)} WHERE {pk_field} = ?"
        set_values.append(pk_value)
        await self._db.execute(sql, set_values)

    async def delete(self) -> None:
        """Delete this instance."""
        if self._db is None:
            raise RuntimeError("Model not bound to a database.")

        pk_field = self._meta["primary_key"]
        pk_value = getattr(self, pk_field)
        if pk_value is None:
            return

        table = self._meta["tablename"]
        sql = f"DELETE FROM {table} WHERE {pk_field} = ?"
        await self._db.execute(sql, [pk_value])
        setattr(self, pk_field, None)

    async def update(self, **kwargs: Any) -> None:
        """Update specific fields and save to database."""
        if self._db is None:
            raise RuntimeError("Model not bound to a database.")

        pk_field = self._meta["primary_key"]
        pk_value = getattr(self, pk_field)
        if pk_value is None:
            raise RuntimeError("Cannot update unsaved instance.")

        for fname, value in kwargs.items():
            if fname in self._meta["fields"]:
                setattr(self, fname, value)

        await self._update()

    @classmethod
    def bind(cls, db: "Database") -> None:
        """Bind the model to a database."""
        cls._db = db

    @classmethod
    async def create(cls, **kwargs: Any) -> "Model":
        """Create and save a new instance."""
        instance = cls(**kwargs)
        instance._db = cls._db
        await instance.save()
        return instance

    @classmethod
    async def get(cls, **kwargs: Any) -> Optional["Model"]:
        """Get a single instance by primary key or filters."""
        if cls._db is None:
            raise RuntimeError("Model not bound to a database.")
        qs = QuerySet(cls, cls._db).filter(**kwargs).limit(1)
        return await qs.first()

    @classmethod
    async def get_or_create(cls, defaults: Optional[Dict] = None, **kwargs: Any) -> Tuple["Model", bool]:
        """Get an existing instance or create a new one."""
        instance = await cls.get(**kwargs)
        if instance:
            return instance, False
        create_kwargs = {**kwargs}
        if defaults:
            create_kwargs.update(defaults)
        instance = await cls.create(**create_kwargs)
        return instance, True

    @classmethod
    def filter(cls, **kwargs: Any) -> QuerySet:
        """Filter instances."""
        if cls._db is None:
            raise RuntimeError("Model not bound to a database.")
        return QuerySet(cls, cls._db).filter(**kwargs)

    @classmethod
    def all(cls) -> QuerySet:
        """Get all instances."""
        if cls._db is None:
            raise RuntimeError("Model not bound to a database.")
        return QuerySet(cls, cls._db)

    @classmethod
    async def count(cls, **kwargs: Any) -> int:
        if cls._db is None:
            raise RuntimeError("Model not bound to a database.")
        qs = QuerySet(cls, cls._db).filter(**kwargs)
        return await qs.count()

    @classmethod
    async def exists(cls, **kwargs: Any) -> bool:
        if cls._db is None:
            raise RuntimeError("Model not bound to a database.")
        qs = QuerySet(cls, cls._db).filter(**kwargs)
        return await qs.exists()

    @classmethod
    async def bulk_create(cls, instances: List["Model"]) -> None:
        """Bulk insert instances."""
        if cls._db is None:
            raise RuntimeError("Model not bound to a database.")
        if not instances:
            return

        meta = cls._meta
        fields_list = []
        all_values = []

        for fname, field in meta["fields"].items():
            if field.primary_key:
                continue
            fields_list.append(fname)

        for inst in instances:
            row = []
            for fname in fields_list:
                field = meta["fields"][fname]
                value = getattr(inst, fname, None)
                if hasattr(field, "auto_now_add") and field.auto_now_add and value is None:
                    value = datetime.now(timezone.utc)
                    setattr(inst, fname, value)
                row.append(field.to_db(value))
            all_values.append(row)

        table = meta["tablename"]
        placeholders = ", ".join(["?"] * len(fields_list))
        sql = f"INSERT INTO {table} ({', '.join(fields_list)}) VALUES ({placeholders})"
        await cls._db.executemany(sql, all_values)


# ═══════════════════════════════════════════════════════════════════════
# Database connection
# ═══════════════════════════════════════════════════════════════════════

class Database:
    """Async database connection manager.

    Supports:
    - SQLite (via aiosqlite)
    - PostgreSQL (via asyncpg)

    Usage::

        db = Database("sqlite:///app.db")
        # or
        db = Database("postgresql://user:pass@localhost/db")

        # Bind models
        User.bind(db)

        # Create tables
        await db.create_all()

        # Use connection directly
        rows = await db.fetch_all("SELECT * FROM users")
    """

    def __init__(self, url: str, **kwargs: Any) -> None:
        self.url = url
        self._kwargs = kwargs
        self._conn = None
        self._dialect = self._parse_dialect(url)
        self._models: List[type] = []
        self._connect_lock = asyncio.Lock()

    def _parse_dialect(self, url: str) -> str:
        if url.startswith("sqlite"):
            return "sqlite"
        elif url.startswith("postgresql"):
            return "postgresql"
        elif url.startswith("mysql"):
            raise ValueError("MySQL is not supported. Use PostgreSQL or SQLite.")
        else:
            raise ValueError(f"Unsupported database URL scheme: {url.split('://')[0] if '://' in url else url}")

    async def connect(self) -> None:
        """Establish database connection."""
        async with self._connect_lock:
            if self._conn is not None:
                return

            if self._dialect == "sqlite":
                try:
                    import aiosqlite
                except ImportError:
                    raise ImportError(
                        "aiosqlite is required for SQLite. "
                        "Install with: pip install fenrir-framework[sqlite]"
                    )
                db_path = self.url.replace("sqlite:///", "").replace("sqlite://", "")
                conn = await aiosqlite.connect(db_path)
                try:
                    conn.row_factory = aiosqlite.Row
                    await conn.execute("PRAGMA journal_mode=WAL")
                    await conn.execute("PRAGMA foreign_keys=ON")
                except Exception:
                    await conn.close()
                    raise
                self._conn = conn
            elif self._dialect == "postgresql":
                try:
                    import asyncpg
                except ImportError:
                    raise ImportError(
                        "asyncpg is required for PostgreSQL. "
                        "Install with: pip install fenrir-framework[postgresql]"
                    )
                self._conn = await asyncpg.connect(self.url)

    async def disconnect(self) -> None:
        """Close database connection."""
        if self._conn is not None:
            try:
                await self._conn.close()
            finally:
                self._conn = None

    async def execute(self, sql: str, params: Optional[List[Any]] = None) -> Any:
        """Execute a query and return cursor/last row id."""
        if self._conn is None:
            await self.connect()
        if self._dialect == "sqlite":
            cursor = await self._conn.execute(sql, params or [])
            await self._conn.commit()
            return cursor.lastrowid
        else:
            result = await self._conn.execute(sql, params or [])
            await self._conn.commit()
            return result

    async def fetch_one(self, sql: str, params: Optional[List[Any]] = None) -> Optional[Dict[str, Any]]:
        """Fetch a single row."""
        if self._conn is None:
            await self.connect()
        if self._dialect == "sqlite":
            cursor = await self._conn.execute(sql, params or [])
            row = await cursor.fetchone()
            if row:
                return dict(row)
            return None
        else:
            row = await self._conn.fetchrow(sql, params or [])
            if row:
                return dict(row)
            return None

    async def fetch_all(self, sql: str, params: Optional[List[Any]] = None) -> List[Dict[str, Any]]:
        """Fetch all rows."""
        if self._conn is None:
            await self.connect()
        if self._dialect == "sqlite":
            cursor = await self._conn.execute(sql, params or [])
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
        else:
            rows = await self._conn.fetch(sql, params or [])
            return [dict(row) for row in rows]

    async def executemany(self, sql: str, params_list: List[List[Any]]) -> None:
        """Execute many queries."""
        if self._conn is None:
            await self.connect()
        if self._dialect == "sqlite":
            await self._conn.executemany(sql, params_list)
            await self._conn.commit()
        else:
            await self._conn.executemany(sql, params_list)
            await self._conn.commit()

    def register_model(self, model_class: type) -> None:
        """Register a model class for auto table creation."""
        self._models.append(model_class)
        model_class.bind(self)

    async def create_all(self) -> None:
        """Create tables for all registered models."""
        if self._conn is None:
            await self.connect()

        for model_class in self._models:
            await self._create_table(model_class)

    async def _create_table(self, model_class: type) -> None:
        """Create a table for a model."""
        meta = model_class._meta
        table = meta["tablename"]
        columns = []

        for fname, field in meta["fields"].items():
            col_type = field.get_column_type(self._dialect)
            parts = [fname, col_type]
            if not field.null and not field.primary_key:
                parts.append("NOT NULL")
            if field.unique and not field.primary_key:
                parts.append("UNIQUE")
            default = field.sql_default()
            if default:
                parts.append(default)
            columns.append(" ".join(parts))

        sql = f"CREATE TABLE IF NOT EXISTS {table} ({', '.join(columns)})"
        await self.execute(sql)

    async def drop_all(self) -> None:
        """Drop all registered model tables in reverse dependency order."""
        for model_class in reversed(self._models):
            table = model_class._meta["tablename"]
            await self.execute(f"DROP TABLE IF EXISTS {table}")

    async def __aenter__(self) -> "Database":
        await self.connect()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.disconnect()


# ═══════════════════════════════════════════════════════════════════════
# Fields namespace for convenient import
# ═══════════════════════════════════════════════════════════════════════

class fields:
    """Namespace for ORM field types.

    Usage::

        from fenrir.orm import Model, fields

        class User(Model):
            id = fields.Integer(primary_key=True)
            name = fields.String(max_length=100)
    """
    Integer = Integer
    String = String
    Text = Text
    Float = Float
    Boolean = Boolean
    Datetime = Datetime
    JSONField = JSONField
