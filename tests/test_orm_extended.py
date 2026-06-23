"""Tests for fenrir.orm module — Extended coverage."""
import pytest
import tempfile
import os

try:
    import aiosqlite
    HAS_AIOSQLITE = True
except ImportError:
    HAS_AIOSQLITE = False

from fenrir.orm import Database, Model, fields, QuerySet, Field

pytestmark = pytest.mark.skipif(not HAS_AIOSQLITE, reason="aiosqlite not installed")


# ═══════════════════════════════════════════════════════════════════════
# Field Base Class Tests
# ═══════════════════════════════════════════════════════════════════════

class TestFieldBase:
    def test_init_defaults(self):
        f = Field()
        assert f.primary_key is False
        assert f.default is None
        assert f.null is True
        assert f.unique is False
        assert f.index is False
        assert f.column_name is None
        assert f.name == ""

    def test_contribute_to_class(self):
        f = Field()
        f.contribute_to_class(type, "myfield")
        assert f.name == "myfield"
        assert f.column_name == "myfield"

    def test_contribute_to_class_custom_column(self):
        f = Field(column_name="custom_col")
        f.contribute_to_class(type, "myfield")
        assert f.column_name == "custom_col"

    def test_get_column_type_not_implemented(self):
        with pytest.raises(NotImplementedError):
            Field().get_column_type()

    def test_sql_literal_none(self):
        f = Field()
        assert f._sql_literal(None) == "NULL"

    def test_sql_literal_bool(self):
        f = Field()
        assert f._sql_literal(True) == "1"
        assert f._sql_literal(False) == "0"

    def test_sql_literal_int(self):
        f = Field()
        assert f._sql_literal(42) == "42"

    def test_sql_literal_float(self):
        f = Field()
        assert f._sql_literal(3.14) == "3.14"

    def test_sql_literal_string(self):
        f = Field()
        assert f._sql_literal("hello") == "'hello'"

    def test_sql_literal_string_escape(self):
        f = Field()
        assert f._sql_literal("it's") == "'it''s'"

    def test_sql_literal_other(self):
        f = Field()
        assert f._sql_literal([1, 2]) == "'[1, 2]'"

    def test_sql_default_with_value(self):
        f = Field(default=42)
        assert "DEFAULT 42" in f.sql_default()

    def test_sql_default_with_string(self):
        f = Field(default="hello")
        assert "DEFAULT 'hello'" in f.sql_default()

    def test_sql_default_callable(self):
        f = Field(default=lambda: 42)
        assert f.sql_default() == ""

    def test_sql_default_null(self):
        f = Field(null=True)
        assert f.sql_default() == ""

    def test_to_python_base(self):
        assert Field().to_python("value") == "value"
        assert Field().to_python(None) is None

    def test_to_db_base(self):
        assert Field().to_db("value") == "value"
        assert Field().to_db(None) is None


# ═══════════════════════════════════════════════════════════════════════
# Field Type Tests
# ═══════════════════════════════════════════════════════════════════════

class TestFieldTypeInteger:
    def test_postgresql_serial(self):
        f = fields.Integer(primary_key=True)
        assert f.get_column_type("postgresql") == "SERIAL PRIMARY KEY"

    def test_to_python_invalid(self):
        f = fields.Integer()
        assert f.to_python("not_a_number") is None

    def test_default(self):
        f = fields.Integer(default=0)
        assert f.default == 0


class TestFieldTypeString:
    def test_default_max_length(self):
        f = fields.String()
        assert f.max_length == 255


class TestFieldTypeFloat:
    def test_to_python_invalid(self):
        f = fields.Float()
        assert f.to_python("not_float") is None


class TestFieldTypeBoolean:
    def test_to_db_none(self):
        f = fields.Boolean()
        assert f.to_db(None) is None


class TestFieldTypeDatetime:
    def test_to_python_string(self):
        f = fields.Datetime()
        result = f.to_python("2024-01-15T12:00:00")
        from datetime import datetime
        assert result == datetime(2024, 1, 15, 12, 0)

    def test_to_python_invalid_string(self):
        f = fields.Datetime()
        assert f.to_python("not-a-date") is None

    def test_to_python_non_string(self):
        f = fields.Datetime()
        assert f.to_python(12345) is None

    def test_to_db_string(self):
        f = fields.Datetime()
        from datetime import datetime
        dt = datetime(2024, 1, 15, 12, 0)
        assert f.to_db(dt) == "2024-01-15T12:00:00"

    def test_to_db_non_datetime(self):
        f = fields.Datetime()
        assert f.to_db("2024-01-15") == "2024-01-15"


class TestFieldTypeJSON:
    def test_to_python_dict(self):
        f = fields.JSONField()
        assert f.to_python({"key": "value"}) == {"key": "value"}

    def test_to_python_list(self):
        f = fields.JSONField()
        assert f.to_python([1, 2]) == [1, 2]

    def test_to_python_string(self):
        f = fields.JSONField()
        assert f.to_python('{"key": "value"}') == {"key": "value"}

    def test_to_python_invalid_string(self):
        f = fields.JSONField()
        assert f.to_python("not json") is None

    def test_to_python_other(self):
        f = fields.JSONField()
        assert f.to_python(42) == 42

    def test_to_db_dict(self):
        f = fields.JSONField()
        result = f.to_db({"key": "value"})
        assert '"key"' in result

    def test_to_db_non_serializable(self):
        f = fields.JSONField()
        with pytest.raises(ValueError, match="Cannot serialize"):
            f.to_db(object())


# ═══════════════════════════════════════════════════════════════════════
# QuerySet Tests
# ═══════════════════════════════════════════════════════════════════════

class TestQuerySet:
    @pytest.fixture
    def db_and_model(self, tmp_path):
        return str(tmp_path / "test.db")

    def test_clone(self):
        from unittest.mock import MagicMock
        mock_db = MagicMock()
        qs = QuerySet(type, mock_db)
        qs._filters = [("name", "eq", "test")]
        qs._order = ["name"]
        qs._limit = 10
        qs._offset = 5

        clone = qs._clone()
        assert clone._filters == [("name", "eq", "test")]
        assert clone._order == ["name"]
        assert clone._limit == 10
        assert clone._offset == 5
        # Ensure independent copies
        clone._filters.append(("age", "gt", 18))
        assert len(qs._filters) == 1

    def test_escape_like(self):
        assert QuerySet._escape_like("100%") == "100\\%"
        assert QuerySet._escape_like("test_") == "test\\_"
        assert QuerySet._escape_like("normal") == "normal"

    def test_build_order_empty(self):
        from unittest.mock import MagicMock
        qs = QuerySet(type, MagicMock())
        assert qs._build_order() == ""

    def test_build_order_invalid_field(self):
        from unittest.mock import MagicMock

        class FakeModel:
            _meta = {"fields": {"name": MagicMock(column_name="name")}}
        qs = QuerySet(FakeModel, MagicMock())
        qs._order = ["nonexistent"]
        assert qs._build_order() == ""

    def test_build_order_with_column_name(self):
        from unittest.mock import MagicMock

        class FakeModel:
            _meta = {"fields": {"name": MagicMock(column_name="custom_name")}}
        qs = QuerySet(FakeModel, MagicMock())
        qs._order = ["name"]
        result = qs._build_order()
        assert "custom_name ASC" in result

    def test_build_order_desc(self):
        from unittest.mock import MagicMock

        class FakeModel:
            _meta = {"fields": {"name": MagicMock(column_name="name")}}
        qs = QuerySet(FakeModel, MagicMock())
        qs._order = ["-name"]
        result = qs._build_order()
        assert "name DESC" in result

    def test_build_where_empty(self):
        from unittest.mock import MagicMock
        qs = QuerySet(type, MagicMock())
        where, params = qs._build_where()
        assert where == ""
        assert params == []

    def test_build_where_in_empty(self):
        from unittest.mock import MagicMock

        class FakeModel:
            _meta = {"fields": {"id": MagicMock(column_name="id")}}
        qs = QuerySet(FakeModel, MagicMock())
        qs._filters = [("id", "in", [])]
        where, params = qs._build_where()
        assert "0" in where

    def test_build_where_not_in_empty(self):
        from unittest.mock import MagicMock

        class FakeModel:
            _meta = {"fields": {"id": MagicMock(column_name="id")}}
        qs = QuerySet(FakeModel, MagicMock())
        qs._filters = [("id", "not_in", [])]
        where, params = qs._build_where()
        assert where == ""


# ═══════════════════════════════════════════════════════════════════════
# Database Tests
# ═══════════════════════════════════════════════════════════════════════

class TestDatabaseInit:
    def test_init_sqlite(self, tmp_path):
        db = Database(f"sqlite:///{tmp_path / 'test.db'}")
        assert db._dialect == "sqlite"

    def test_init_invalid_scheme(self):
        with pytest.raises(ValueError, match="MySQL is not supported"):
            Database("mysql://localhost/test")

    def test_init_postgresql(self):
        db = Database("postgresql://user:pass@localhost/test")
        assert db._dialect == "postgresql"


# ═══════════════════════════════════════════════════════════════════════
# Model Meta Tests
# ═══════════════════════════════════════════════════════════════════════

class TestModelMeta:
    def test_model_tablename(self):
        class MyModel(Model):
            __tablename__ = "my_table"
            id = fields.Integer(primary_key=True)

        assert MyModel._meta["tablename"] == "my_table"

    def test_model_auto_tablename(self):
        class AnotherModel(Model):
            id = fields.Integer(primary_key=True)

        assert AnotherModel._meta["tablename"] == "anothermodels"

    def test_model_fields(self):
        class ItemModel(Model):
            __tablename__ = "items"
            id = fields.Integer(primary_key=True)
            name = fields.String(max_length=100)
            price = fields.Float(default=0.0)

        assert "id" in ItemModel._meta["fields"]
        assert "name" in ItemModel._meta["fields"]
        assert "price" in ItemModel._meta["fields"]
        assert ItemModel._meta["fields"]["name"].max_length == 100
