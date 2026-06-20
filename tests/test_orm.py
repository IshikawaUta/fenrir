"""Tests for fenrir.orm — Lightweight async ORM."""
import asyncio
import pytest
import tempfile
import os

try:
    import aiosqlite
    HAS_AIOSQLITE = True
except ImportError:
    HAS_AIOSQLITE = False

from fenrir.orm import Database, Model, fields, QuerySet

pytestmark = pytest.mark.skipif(not HAS_AIOSQLITE, reason="aiosqlite not installed")


# ═══════════════════════════════════════════════════════════════════════
# Field Tests
# ═══════════════════════════════════════════════════════════════════════

class TestFields:
    def test_integer_field(self):
        field = fields.Integer(primary_key=True)
        assert field.get_column_type("sqlite") == "INTEGER PRIMARY KEY AUTOINCREMENT"
        assert field.to_python("123") == 123
        assert field.to_python(None) is None

    def test_string_field(self):
        field = fields.String(max_length=100)
        assert field.get_column_type("sqlite") == "VARCHAR(100)"
        assert field.to_python(123) == "123"

    def test_text_field(self):
        field = fields.Text()
        assert field.get_column_type("sqlite") == "TEXT"

    def test_float_field(self):
        field = fields.Float()
        assert field.get_column_type("sqlite") == "REAL"
        assert field.to_python("3.14") == 3.14

    def test_boolean_field(self):
        field = fields.Boolean()
        assert field.to_python(1) is True
        assert field.to_python(0) is False
        assert field.to_db(True) == 1

    def test_datetime_field(self):
        from datetime import datetime
        field = fields.Datetime()
        now = datetime.now()
        assert field.to_db(now) == now.isoformat()
        assert field.to_python(now.isoformat()) == now

    def test_json_field(self):
        field = fields.JSONField()
        data = {"key": "value"}
        result = field.to_db(data)
        # orjson produces compact JSON
        assert '"key"' in result
        assert '"value"' in result
        assert field.to_python(result) == data

    def test_field_sql_default(self):
        field = fields.Integer(default=42)
        assert "DEFAULT 42" in field.sql_default()

    def test_field_null(self):
        field = fields.String(null=True)
        assert "NOT NULL" not in field.sql_default()


# ═══════════════════════════════════════════════════════════════════════
# Model Tests
# ═══════════════════════════════════════════════════════════════════════

class TestModel:
    def test_model_creation(self):
        class User(Model):
            __tablename__ = "users"
            id = fields.Integer(primary_key=True)
            name = fields.String(max_length=100)
        
        user = User(name="Alice")
        assert user.name == "Alice"
        assert user.id is None

    def test_model_to_dict(self):
        class User(Model):
            __tablename__ = "users"
            id = fields.Integer(primary_key=True)
            name = fields.String(max_length=100)
        
        user = User(id=1, name="Alice")
        data = user.to_dict()
        assert data["id"] == 1
        assert data["name"] == "Alice"

    def test_model_default_primary_key(self):
        class Item(Model):
            __tablename__ = "items"
            name = fields.String(max_length=100)
        
        assert "id" in Item._meta["fields"]
        assert Item._meta["fields"]["id"].primary_key is True

    def test_model_tablename(self):
        class User(Model):
            __tablename__ = "users"
            name = fields.String(max_length=100)
        
        assert User._meta["tablename"] == "users"

    def test_model_custom_tablename(self):
        class MyModel(Model):
            __tablename__ = "custom_table"
            name = fields.String(max_length=100)
        
        assert MyModel._meta["tablename"] == "custom_table"


# ═══════════════════════════════════════════════════════════════════════
# Database Tests
# ═══════════════════════════════════════════════════════════════════════

class TestDatabase:
    def test_database_creation(self):
        db = Database("sqlite:///:memory:")
        assert db._dialect == "sqlite"

    def test_database_parse_dialect(self):
        assert Database("sqlite:///test.db")._dialect == "sqlite"
        assert Database("postgresql://localhost")._dialect == "postgresql"

    @pytest.mark.anyio
    async def test_database_connect_disconnect(self):
        db = Database("sqlite:///:memory:")
        await db.connect()
        assert db._conn is not None
        await db.disconnect()
        assert db._conn is None

    @pytest.mark.anyio
    async def test_database_execute(self):
        db = Database("sqlite:///:memory:")
        await db.connect()
        result = await db.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, name TEXT)")
        assert result is not None
        await db.disconnect()

    @pytest.mark.anyio
    async def test_database_fetch_one(self):
        db = Database("sqlite:///:memory:")
        await db.connect()
        await db.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, name TEXT)")
        await db.execute("INSERT INTO test (name) VALUES (?)", ["Alice"])
        row = await db.fetch_one("SELECT * FROM test WHERE name = ?", ["Alice"])
        assert row is not None
        assert row["name"] == "Alice"
        await db.disconnect()

    @pytest.mark.anyio
    async def test_database_fetch_all(self):
        db = Database("sqlite:///:memory:")
        await db.connect()
        await db.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, name TEXT)")
        await db.execute("INSERT INTO test (name) VALUES (?)", ["Alice"])
        await db.execute("INSERT INTO test (name) VALUES (?)", ["Bob"])
        rows = await db.fetch_all("SELECT * FROM test")
        assert len(rows) == 2
        await db.disconnect()


# ═══════════════════════════════════════════════════════════════════════
# ORM Integration Tests
# ═══════════════════════════════════════════════════════════════════════

class TestORMIntegration:
    @pytest.mark.anyio
    async def test_create_table(self):
        class User(Model):
            __tablename__ = "test_users"
            id = fields.Integer(primary_key=True)
            name = fields.String(max_length=100)
        
        db = Database("sqlite:///:memory:")
        db.register_model(User)
        await db.create_all()
        
        row = await db.fetch_one("SELECT name FROM sqlite_master WHERE type='table' AND name='test_users'")
        assert row is not None
        await db.disconnect()

    @pytest.mark.anyio
    async def test_crud_operations(self):
        class User(Model):
            __tablename__ = "crud_users"
            id = fields.Integer(primary_key=True)
            name = fields.String(max_length=100)
            email = fields.String(max_length=255)
        
        db = Database("sqlite:///:memory:")
        db.register_model(User)
        await db.create_all()
        User.bind(db)
        
        user = await User.create(name="Alice", email="alice@example.com")
        assert user.id is not None
        assert user.name == "Alice"
        
        user2 = await User.get(id=user.id)
        assert user2 is not None
        assert user2.name == "Alice"
        
        await user.update(name="Alice Smith")
        user3 = await User.get(id=user.id)
        assert user3.name == "Alice Smith"
        
        await user.delete()
        user4 = await User.get(id=user.id)
        assert user4 is None
        
        await db.disconnect()

    @pytest.mark.anyio
    async def test_filter(self):
        class User(Model):
            __tablename__ = "filter_users"
            id = fields.Integer(primary_key=True)
            name = fields.String(max_length=100)
            age = fields.Integer(default=0)
        
        db = Database("sqlite:///:memory:")
        db.register_model(User)
        await db.create_all()
        User.bind(db)
        
        await User.create(name="Alice", age=25)
        await User.create(name="Bob", age=30)
        await User.create(name="Charlie", age=35)
        
        users = await User.filter(age__gte=30).all()
        assert len(users) == 2
        
        users = await User.all().order_by("-age")
        assert users[0].name == "Charlie"
        
        await db.disconnect()

    @pytest.mark.anyio
    async def test_count(self):
        class User(Model):
            __tablename__ = "count_users"
            id = fields.Integer(primary_key=True)
            name = fields.String(max_length=100)
        
        db = Database("sqlite:///:memory:")
        db.register_model(User)
        await db.create_all()
        User.bind(db)
        
        await User.create(name="Alice")
        await User.create(name="Bob")
        
        count = await User.count()
        assert count == 2
        
        await db.disconnect()
