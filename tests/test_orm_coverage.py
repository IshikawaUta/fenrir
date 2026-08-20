"""Tests for fenrir.orm — edge/branch coverage."""

import importlib.util
import sys
from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

HAS_AIOSQLITE = importlib.util.find_spec("aiosqlite") is not None

from fenrir.orm import Database, Field, Model, QuerySet, fields

pytestmark = pytest.mark.skipif(not HAS_AIOSQLITE, reason="aiosqlite not installed")


class TestFieldEdges:
    def test_string_to_python_none(self):
        assert fields.String().to_python(None) is None

    def test_float_to_python_none(self):
        assert fields.Float().to_python(None) is None

    def test_boolean_get_column_type(self):
        assert fields.Boolean().get_column_type("sqlite") == "INTEGER"

    def test_boolean_to_python_none(self):
        assert fields.Boolean().to_python(None) is None

    def test_datetime_get_column_type(self):
        assert fields.Datetime().get_column_type("sqlite") == "TEXT"

    def test_datetime_to_python_none(self):
        assert fields.Datetime().to_python(None) is None

    def test_datetime_to_python_instance(self):
        now = datetime.now()
        assert fields.Datetime().to_python(now) is now

    def test_datetime_to_db_none(self):
        assert fields.Datetime().to_db(None) is None

    def test_jsonfield_get_column_type(self):
        assert fields.JSONField().get_column_type("sqlite") == "TEXT"

    def test_jsonfield_stdjson_paths(self):
        from fenrir import orm as orm_mod
        field = fields.JSONField()
        with patch.object(orm_mod, "_HAS_ORJSON", False):
            assert field.to_python('{"k": 1}') == {"k": 1}
            assert field.to_db({"k": 1}) == '{"k": 1}'

    def test_jsonfield_to_python_none(self):
        assert fields.JSONField().to_python(None) is None

    def test_jsonfield_to_db_none(self):
        assert fields.JSONField().to_db(None) is None

    def test_sql_default_null_false(self):
        assert Field(null=False).sql_default() == ""


class TestQuerySetBuild:
    def _qs(self, fields_map, tablename="users"):
        class FakeModel:
            _meta = {"tablename": tablename, "fields": fields_map}

            @classmethod
            def _from_row(cls, row):
                return row

        return QuerySet(FakeModel, MagicMock())

    def test_filter_invalid_field(self):
        qs = self._qs({"id": MagicMock(column_name="id")})
        with pytest.raises(ValueError, match="Invalid filter field"):
            qs.filter(unknown=1)

    def test_exclude_basic(self):
        qs = self._qs({"name": MagicMock(column_name="name")})
        out = qs.exclude(name="x")
        assert out._filters == [("name", "neq", "x")]
        assert out is not qs

    def test_exclude_operator_inversion(self):
        qs = self._qs({"age": MagicMock(column_name="age")})
        out = qs.exclude(age__gt=18)
        assert out._filters == [("age", "lte", 18)]

    def test_exclude_unknown_operator(self):
        qs = self._qs({"age": MagicMock(column_name="age")})
        out = qs.exclude(age__custom=1)
        assert out._filters == [("age", "not_custom", 1)]

    def test_exclude_invalid_field(self):
        qs = self._qs({"id": MagicMock(column_name="id")})
        with pytest.raises(ValueError, match="Invalid filter field"):
            qs.exclude(unknown=1)

    def test_offset(self):
        qs = self._qs({"id": MagicMock(column_name="id")})
        out = qs.offset(5)
        assert out._offset == 5

    def test_build_where_all_operators(self):
        qs = self._qs({
            "a": MagicMock(column_name="a"),
            "b": MagicMock(column_name="b"),
            "c": MagicMock(column_name="c"),
            "d": MagicMock(column_name="d"),
        })
        qs._filters = [
            ("a", "neq", 1),
            ("a", "gt", 1),
            ("a", "gte", 1),
            ("a", "lt", 1),
            ("a", "lte", 1),
            ("b", "contains", "x"),
            ("b", "startswith", "x"),
            ("b", "endswith", "x"),
            ("b", "not_contains", "x"),
            ("b", "not_startswith", "x"),
            ("b", "not_endswith", "x"),
            ("c", "in", [1, 2]),
            ("c", "not_in", [1, 2]),
            ("d", "isnull", True),
            ("d", "isnull", False),
            ("d", "not_isnull", True),
            ("d", "not_isnull", False),
            ("e", "unknown_op", 1),
        ]
        where, params = qs._build_where()
        assert "a != ?" in where
        assert "a > ?" in where
        assert "a >= ?" in where
        assert "a < ?" in where
        assert "a <= ?" in where
        assert "LIKE ? ESCAPE" in where
        assert "NOT LIKE ? ESCAPE" in where
        assert "IN (?, ?)" in where
        assert "NOT IN (?, ?)" in where
        assert "IS NULL" in where
        assert "IS NOT NULL" in where
        assert "%x%" in params
        assert "x%" in params
        assert 1 in params
        assert 2 in params

    def test_safe_table_invalid(self):
        qs = self._qs({"id": MagicMock(column_name="id")}, tablename="ta;ble")
        with pytest.raises(ValueError, match="Invalid table name"):
            qs._safe_table()

    def test_build_order_missing_column_name(self):
        qs = self._qs({"name": MagicMock(column_name=None)})
        qs._order = ["name"]
        assert "name ASC" in qs._build_order()


class TestQuerySetAsync:
    def _db(self):
        return MagicMock()

    def _qs(self, db, fields_map=None):
        class FakeModel:
            _meta = {
                "tablename": "users",
                "fields": fields_map or {"id": MagicMock(column_name="id")},
            }

            @classmethod
            def _from_row(cls, row):
                return row

        return QuerySet(FakeModel, db)

    @pytest.mark.anyio
    async def test_fetch_all_with_limit_offset(self):
        db = self._db()
        db.fetch_all = AsyncMock(return_value=[{"id": 1}])
        qs = self._qs(db)
        qs._limit = 2
        qs._offset = 1
        rows = await qs._fetch_all()
        assert rows == [{"id": 1}]
        sql = db.fetch_all.await_args.args[0]
        assert "LIMIT 2" in sql
        assert "OFFSET 1" in sql

    @pytest.mark.anyio
    async def test_exists_true_and_false(self):
        db = self._db()
        db.fetch_one = AsyncMock(side_effect=[{"cnt": 0}, {"cnt": 2}])
        qs = self._qs(db)
        assert await qs.exists() is False
        assert await qs.exists() is True

    @pytest.mark.anyio
    async def test_delete(self):
        db = self._db()
        db.execute = AsyncMock(return_value=3)
        qs = self._qs(db)
        qs._filters = [("id", "gt", 0)]
        assert await qs.delete() == 3
        sql = db.execute.await_args.args[0]
        assert sql.startswith("DELETE FROM users")

    @pytest.mark.anyio
    async def test_update(self):
        field = fields.String()
        field.column_name = "name"
        db = self._db()
        db.execute = AsyncMock(return_value=1)
        qs = self._qs(db, {"id": MagicMock(column_name="id"), "name": field})
        qs._filters = [("id", "eq", 1)]
        result = await qs.update(name="Bob")
        assert result == 1
        sql, params = db.execute.await_args.args
        assert "UPDATE users SET name = ?" in sql
        assert params == ["Bob", 1]

    @pytest.mark.anyio
    async def test_update_invalid_field(self):
        db = self._db()
        qs = self._qs(db)
        with pytest.raises(ValueError, match="Invalid field name"):
            await qs.update(nope=1)

    @pytest.mark.anyio
    async def test_update_none_field_obj(self):
        class FakeModel:
            _meta = {"tablename": "users", "fields": {"id": None}}

        db = self._db()
        db.execute = AsyncMock(return_value=1)
        qs = QuerySet(FakeModel, db)
        result = await qs.update(id=5)
        assert result == 1
        sql = db.execute.await_args.args[0]
        assert "SET id = ?" in sql


class TestModelMetaEdges:
    def test_inherited_fields(self):
        class Parent(Model):
            __tablename__ = "parents"
            id = fields.Integer(primary_key=True)
            name = fields.String(max_length=50)

        class Child(Parent):
            age = fields.Integer(default=0)

        assert set(Child._meta["fields"]) == {"id", "name", "age"}
        assert Child._meta["primary_key"] == "id"
        assert Child._meta["fields"]["name"].model_class is Parent

    def test_non_model_base(self):
        class Mixin:
            pass

        class M(Model, Mixin):
            x = fields.Integer()

        assert "x" in M._meta["fields"]
        assert "id" in M._meta["fields"]


class TestModelEdges:
    def test_init_defaults(self):
        class M(Model):
            id = fields.Integer(primary_key=True)
            cb = fields.Integer(default=lambda: 99)
            plain = fields.Integer(default=7)
            nothing = fields.String(null=True)

        inst = M()
        assert inst.id is None
        assert inst.cb == 99
        assert inst.plain == 7
        assert inst.nothing is None

    def test_init_unknown_kwarg(self):
        class M(Model):
            id = fields.Integer(primary_key=True)

        with pytest.raises(TypeError, match="unexpected keyword argument 'nope'"):
            M(nope=1)

    def test_from_row_tuple(self):
        class M(Model):
            id = fields.Integer(primary_key=True)
            name = fields.String(max_length=50)

        inst = M._from_row((5, "Bob"))
        assert inst.id == 5
        assert inst.name == "Bob"

    def test_from_row_object(self):
        class M(Model):
            id = fields.Integer(primary_key=True)
            name = fields.String(max_length=50)

        row = SimpleNamespace(id=9, name="Ana")
        inst = M._from_row(row)
        assert inst.id == 9
        assert inst.name == "Ana"

    def test_from_row_other(self):
        class M(Model):
            id = fields.Integer(primary_key=True)
            name = fields.String(max_length=50)

        inst = M._from_row(123)
        assert inst.id is None
        assert inst.name is None

    def test_to_dict_datetime_and_iso(self):
        class M(Model):
            id = fields.Integer(primary_key=True)
            at = fields.Datetime(null=True)
            day = fields.String(null=True)

        inst = M(id=1, at=datetime(2024, 1, 2, 3, 4))
        inst.day = date(2020, 5, 6)
        data = inst.to_dict()
        assert data["at"] == "2024-01-02T03:04:00"
        assert data["day"] == "2020-05-06"

    @pytest.mark.anyio
    async def test_save_unbound(self):
        class M(Model):
            id = fields.Integer(primary_key=True)

        with pytest.raises(RuntimeError, match="not bound"):
            await M().save()

    @pytest.mark.anyio
    async def test_save_updates_when_pk_set(self):
        class M(Model):
            __tablename__ = "save_upd"
            id = fields.Integer(primary_key=True)
            name = fields.String(max_length=50)

        db = Database("sqlite:///:memory:")
        db.register_model(M)
        await db.create_all()

        inst = M(name="A")
        inst._db = db
        await inst.save()
        inst.name = "B"
        await inst.save()
        assert (await db.fetch_all("SELECT * FROM save_upd"))[0]["name"] == "B"
        await db.disconnect()

    @pytest.mark.anyio
    async def test_insert_auto_now_add(self):
        class M(Model):
            __tablename__ = "auto_add"
            id = fields.Integer(primary_key=True)
            at = fields.Datetime(auto_now_add=True)

        db = Database("sqlite:///:memory:")
        db.register_model(M)
        await db.create_all()

        inst = M()
        inst._db = db
        await inst.save()
        assert inst.at is not None
        await db.disconnect()

    @pytest.mark.anyio
    async def test_update_auto_now(self):
        class M(Model):
            __tablename__ = "auto_now"
            id = fields.Integer(primary_key=True)
            at = fields.Datetime(auto_now=True)

        db = Database("sqlite:///:memory:")
        db.register_model(M)
        await db.create_all()

        inst = M(id=1)
        inst._db = db
        await inst._update()
        assert inst.at is not None
        await db.disconnect()

    @pytest.mark.anyio
    async def test_delete_unbound(self):
        class M(Model):
            id = fields.Integer(primary_key=True)

        with pytest.raises(RuntimeError, match="not bound"):
            await M(id=1).delete()

    @pytest.mark.anyio
    async def test_delete_unsaved(self):
        class M(Model):
            __tablename__ = "del_unsaved"
            id = fields.Integer(primary_key=True)

        db = Database("sqlite:///:memory:")
        db.register_model(M)
        await db.create_all()

        inst = M()
        inst._db = db
        await inst.delete()
        assert inst.id is None
        await db.disconnect()

    @pytest.mark.anyio
    async def test_update_unbound(self):
        class M(Model):
            id = fields.Integer(primary_key=True)

        with pytest.raises(RuntimeError, match="not bound"):
            await M(id=1).update(name="x")

    @pytest.mark.anyio
    async def test_update_unsaved(self):
        class M(Model):
            __tablename__ = "upd_unsaved"
            id = fields.Integer(primary_key=True)

        db = Database("sqlite:///:memory:")
        db.register_model(M)
        await db.create_all()

        inst = M()
        inst._db = db
        with pytest.raises(RuntimeError, match="unsaved"):
            await inst.update(name="x")
        await db.disconnect()

    @pytest.mark.anyio
    async def test_update_ignores_unknown_field(self):
        class M(Model):
            __tablename__ = "upd_unknown"
            id = fields.Integer(primary_key=True)
            name = fields.String(max_length=50)

        db = Database("sqlite:///:memory:")
        db.register_model(M)
        await db.create_all()

        inst = M(id=1, name="A")
        inst._db = db
        await inst.update(name="B", nope=1)
        assert inst.name == "B"
        await db.disconnect()

    @pytest.mark.anyio
    async def test_get_unbound(self):
        class M(Model):
            id = fields.Integer(primary_key=True)

        with pytest.raises(RuntimeError, match="not bound"):
            await M.get(id=1)

    def test_filter_unbound(self):
        class M(Model):
            id = fields.Integer(primary_key=True)

        with pytest.raises(RuntimeError, match="not bound"):
            M.filter(id=1)

    def test_all_unbound(self):
        class M(Model):
            id = fields.Integer(primary_key=True)

        with pytest.raises(RuntimeError, match="not bound"):
            M.all()

    @pytest.mark.anyio
    async def test_count_unbound(self):
        class M(Model):
            id = fields.Integer(primary_key=True)

        with pytest.raises(RuntimeError, match="not bound"):
            await M.count()

    @pytest.mark.anyio
    async def test_exists_unbound(self):
        class M(Model):
            id = fields.Integer(primary_key=True)

        with pytest.raises(RuntimeError, match="not bound"):
            await M.exists()


class TestClassMethods:
    @pytest.mark.anyio
    async def test_get_or_create(self):
        class M(Model):
            __tablename__ = "goc"
            id = fields.Integer(primary_key=True)
            name = fields.String(max_length=50)
            extra = fields.String(max_length=50, null=True)

        db = Database("sqlite:///:memory:")
        db.register_model(M)
        await db.create_all()

        inst, created = await M.get_or_create(name="A", defaults={"extra": "e1"})
        assert created is True
        assert inst.extra == "e1"

        inst2, created2 = await M.get_or_create(name="A", defaults={"extra": "e2"})
        assert created2 is False
        assert inst2.id == inst.id
        assert inst2.extra == "e1"
        await db.disconnect()

    @pytest.mark.anyio
    async def test_get_or_create_no_defaults(self):
        class M(Model):
            __tablename__ = "goc_nd"
            id = fields.Integer(primary_key=True)
            name = fields.String(max_length=50)

        db = Database("sqlite:///:memory:")
        db.register_model(M)
        await db.create_all()

        inst, created = await M.get_or_create(name="B")
        assert created is True
        assert inst.name == "B"
        await db.disconnect()

    @pytest.mark.anyio
    async def test_exists_with_filter(self):
        class M(Model):
            __tablename__ = "exists_f"
            id = fields.Integer(primary_key=True)
            name = fields.String(max_length=50)

        db = Database("sqlite:///:memory:")
        db.register_model(M)
        await db.create_all()

        await M.create(name="A")
        assert await M.exists(name="A") is True
        assert await M.exists(name="Z") is False
        await db.disconnect()

    @pytest.mark.anyio
    async def test_count_with_filter(self):
        class M(Model):
            __tablename__ = "count_f"
            id = fields.Integer(primary_key=True)
            age = fields.Integer(default=0)

        db = Database("sqlite:///:memory:")
        db.register_model(M)
        await db.create_all()

        await M.create(age=10)
        await M.create(age=20)
        assert await M.count(age__gte=15) == 1
        await db.disconnect()

    @pytest.mark.anyio
    async def test_queryset_delete(self):
        class M(Model):
            __tablename__ = "qs_del"
            id = fields.Integer(primary_key=True)
            name = fields.String(max_length=50)

        db = Database("sqlite:///:memory:")
        db.register_model(M)
        await db.create_all()

        await M.create(name="A")
        await M.create(name="B")
        n = await M.filter(name="A").delete()
        assert n == 2
        assert await M.count() == 1
        await db.disconnect()

    @pytest.mark.anyio
    async def test_queryset_update(self):
        class M(Model):
            __tablename__ = "qs_upd"
            id = fields.Integer(primary_key=True)
            age = fields.Integer(default=0)

        db = Database("sqlite:///:memory:")
        db.register_model(M)
        await db.create_all()

        await M.create(age=10)
        await M.create(age=20)
        n = await M.filter(age__lt=15).update(age=99)
        assert n == 2
        rows = await db.fetch_all("SELECT age FROM qs_upd")
        assert sorted(r["age"] for r in rows) == [20, 99]
        await db.disconnect()

    @pytest.mark.anyio
    async def test_bulk_create(self):
        class M(Model):
            __tablename__ = "bulk"
            id = fields.Integer(primary_key=True)
            name = fields.String(max_length=50)

        db = Database("sqlite:///:memory:")
        db.register_model(M)
        await db.create_all()

        await M.bulk_create([M(name="A"), M(name="B"), M(name="C")])
        assert await M.count() == 3
        await db.disconnect()

    @pytest.mark.anyio
    async def test_bulk_create_empty(self):
        class M(Model):
            __tablename__ = "bulk_empty"
            id = fields.Integer(primary_key=True)

        db = Database("sqlite:///:memory:")
        db.register_model(M)
        await db.create_all()

        await M.bulk_create([])
        await db.disconnect()

    @pytest.mark.anyio
    async def test_bulk_create_auto_now_add(self):
        class M(Model):
            __tablename__ = "bulk_auto"
            id = fields.Integer(primary_key=True)
            at = fields.Datetime(auto_now_add=True)

        db = Database("sqlite:///:memory:")
        db.register_model(M)
        await db.create_all()

        await M.bulk_create([M()])
        rows = await db.fetch_all("SELECT at FROM bulk_auto")
        assert rows[0]["at"] is not None
        await db.disconnect()

    @pytest.mark.anyio
    async def test_bulk_create_unbound(self):
        class M(Model):
            id = fields.Integer(primary_key=True)

        with pytest.raises(RuntimeError, match="not bound"):
            await M.bulk_create([M()])


class TestDatabaseEdges:
    def test_unsupported_scheme(self):
        with pytest.raises(ValueError, match="Unsupported database URL scheme"):
            Database("foo://localhost/x")

    @pytest.mark.anyio
    async def test_connect_twice_and_reconnect(self):
        db = Database("sqlite:///:memory:")
        await db.connect()
        conn1 = db._conn
        await db.connect()
        assert db._conn is conn1
        await db.disconnect()
        await db.connect()
        assert db._conn is not None
        await db.disconnect()
        await db.disconnect()

    @pytest.mark.anyio
    async def test_connect_aiosqlite_missing(self):
        db = Database("sqlite:///x.db")
        with patch.dict(sys.modules, {"aiosqlite": None}):
            with pytest.raises(ImportError, match="aiosqlite is required"):
                await db.connect()

    @pytest.mark.anyio
    async def test_connect_pragma_failure(self):
        class FakeConn:
            def __init__(self):
                self.closed = False

            async def execute(self, *a):
                raise RuntimeError("pragma fail")

            async def close(self):
                self.closed = True

        fake = MagicMock()
        fake.Row = object()
        fake.connect = AsyncMock(return_value=FakeConn())

        db = Database("sqlite:///x.db")
        with patch.dict(sys.modules, {"aiosqlite": fake}):
            with pytest.raises(RuntimeError, match="pragma fail"):
                await db.connect()
        assert db._conn is None

    @pytest.mark.anyio
    async def test_connect_postgres_missing(self):
        db = Database("postgresql://user@localhost/x")
        with patch.dict(sys.modules, {"asyncpg": None}):
            with pytest.raises(ImportError, match="asyncpg is required"):
                await db.connect()

    @pytest.mark.anyio
    async def test_connect_postgres(self):
        fake = MagicMock()
        fake.connect = AsyncMock(return_value="PG_CONN")
        db = Database("postgresql://user@localhost/x")
        with patch.dict(sys.modules, {"asyncpg": fake}):
            await db.connect()
        assert db._conn == "PG_CONN"

    def test_convert_placeholders_escaped_quote(self):
        sql = "SELECT 'it''s' AS q, ?"
        assert Database._convert_placeholders(sql) == "SELECT 'it''s' AS q, $1"

    @pytest.mark.anyio
    async def test_execute_auto_connect(self):
        db = Database("sqlite:///:memory:")
        result = await db.execute("CREATE TABLE auto_t (id INTEGER)")
        assert result is not None
        await db.disconnect()

    @pytest.mark.anyio
    async def test_execute_postgres(self):
        conn = MagicMock()
        conn.execute = AsyncMock(return_value="PGOK")
        conn.commit = AsyncMock()
        db = Database("postgresql://user@localhost/x")
        db._conn = conn
        result = await db.execute("SELECT * FROM t WHERE id = ?", [1])
        assert result == "PGOK"
        sql = conn.execute.await_args.args[0]
        assert "id = $1" in sql
        conn.commit.assert_awaited_once()

    @pytest.mark.anyio
    async def test_fetch_one_auto_connect_and_postgres(self):
        conn = MagicMock()
        conn.fetchrow = AsyncMock(return_value={"id": 1})
        db = Database("postgresql://user@localhost/x")
        db._conn = conn
        row = await db.fetch_one("SELECT * FROM t WHERE id = ?", [1])
        assert row == {"id": 1}
        sql = conn.fetchrow.await_args.args[0]
        assert "id = $1" in sql

    @pytest.mark.anyio
    async def test_fetch_one_postgres_empty(self):
        conn = MagicMock()
        conn.fetchrow = AsyncMock(return_value=None)
        db = Database("postgresql://user@localhost/x")
        db._conn = conn
        assert await db.fetch_one("SELECT 1") is None

    @pytest.mark.anyio
    async def test_fetch_all_postgres(self):
        conn = MagicMock()
        conn.fetch = AsyncMock(return_value=[{"id": 1}, {"id": 2}])
        db = Database("postgresql://user@localhost/x")
        db._conn = conn
        rows = await db.fetch_all("SELECT * FROM t WHERE id = ?", [1])
        assert rows == [{"id": 1}, {"id": 2}]
        assert "id = $1" in conn.fetch.await_args.args[0]

    @pytest.mark.anyio
    async def test_executemany_sqlite(self):
        db = Database("sqlite:///:memory:")
        await db.connect()
        await db.execute("CREATE TABLE em (id INTEGER, name TEXT)")
        await db.executemany("INSERT INTO em VALUES (?, ?)", [[1, "A"], [2, "B"]])
        assert len(await db.fetch_all("SELECT * FROM em")) == 2
        await db.disconnect()

    @pytest.mark.anyio
    async def test_executemany_postgres(self):
        conn = MagicMock()
        conn.executemany = AsyncMock()
        conn.commit = AsyncMock()
        db = Database("postgresql://user@localhost/x")
        db._conn = conn
        await db.executemany("INSERT INTO t VALUES (?)", [[1], [2]])
        assert "VALUES ($1)" in conn.executemany.await_args.args[0]
        conn.commit.assert_awaited_once()

    @pytest.mark.anyio
    async def test_create_all_no_models(self):
        db = Database("sqlite:///:memory:")
        await db.create_all()
        assert db._conn is not None
        await db.disconnect()

    @pytest.mark.anyio
    async def test_create_table_unique(self):
        class M(Model):
            __tablename__ = "uniq_t"
            id = fields.Integer(primary_key=True)
            email = fields.String(max_length=100, unique=True)

        db = Database("sqlite:///:memory:")
        db.register_model(M)
        await db.create_all()
        row = await db.fetch_one("SELECT name FROM sqlite_master WHERE type='table' AND name='uniq_t'")
        assert row is not None
        await db.disconnect()

    @pytest.mark.anyio
    async def test_drop_all(self):
        class M(Model):
            __tablename__ = "drop_t"
            id = fields.Integer(primary_key=True)

        db = Database("sqlite:///:memory:")
        db.register_model(M)
        await db.create_all()
        await db.drop_all()
        row = await db.fetch_one("SELECT name FROM sqlite_master WHERE type='table' AND name='drop_t'")
        assert row is None
        await db.disconnect()

    @pytest.mark.anyio
    async def test_async_context_manager(self):
        class M(Model):
            __tablename__ = "ctx_t"
            id = fields.Integer(primary_key=True)

        db = Database("sqlite:///:memory:")
        db.register_model(M)
        async with db as d:
            assert d._conn is not None
            await d.create_all()
        assert db._conn is None

    @pytest.mark.anyio
    async def test_transaction_auto_connect(self):
        db = Database("sqlite:///:memory:")
        async with db.transaction():
            await db.execute("CREATE TABLE txac (id INTEGER)")
        assert db._conn is not None
        await db.disconnect()

    @pytest.mark.anyio
    async def test_connect_unknown_dialect_noop(self):
        db = Database("postgresql://user@localhost/x")
        db._dialect = "oracle"
        await db.connect()
        assert db._conn is None

    @pytest.mark.anyio
    async def test_execute_postgres_in_transaction(self):
        conn = MagicMock()
        conn.execute = AsyncMock(return_value="PGOK")
        conn.commit = AsyncMock()
        db = Database("postgresql://user@localhost/x")
        db._conn = conn
        db._in_transaction = True
        result = await db.execute("SELECT 1")
        assert result == "PGOK"
        conn.commit.assert_not_awaited()

    @pytest.mark.anyio
    async def test_fetch_one_auto_connect(self, tmp_path):
        db_file = tmp_path / "fetch_one.db"
        setup = Database(f"sqlite:///{db_file}")
        await setup.execute("CREATE TABLE af (id INTEGER)")
        await setup.execute("INSERT INTO af VALUES (?)", [1])
        await setup.disconnect()

        db = Database(f"sqlite:///{db_file}")
        assert await db.fetch_one("SELECT * FROM af") == {"id": 1}
        await db.disconnect()

    @pytest.mark.anyio
    async def test_fetch_all_auto_connect(self, tmp_path):
        db_file = tmp_path / "fetch_all.db"
        setup = Database(f"sqlite:///{db_file}")
        await setup.execute("CREATE TABLE afa (id INTEGER)")
        await setup.execute("INSERT INTO afa VALUES (?)", [1])
        await setup.disconnect()

        db = Database(f"sqlite:///{db_file}")
        assert await db.fetch_all("SELECT * FROM afa") == [{"id": 1}]
        await db.disconnect()

    @pytest.mark.anyio
    async def test_executemany_auto_connect(self, tmp_path):
        db_file = tmp_path / "exec_many.db"
        setup = Database(f"sqlite:///{db_file}")
        await setup.execute("CREATE TABLE am (id INTEGER)")
        await setup.disconnect()

        db = Database(f"sqlite:///{db_file}")
        await db.executemany("INSERT INTO am VALUES (?)", [[1], [2]])
        assert len(await db.fetch_all("SELECT * FROM am")) == 2
        await db.disconnect()

    @pytest.mark.anyio
    async def test_executemany_postgres_in_transaction(self):
        conn = MagicMock()
        conn.executemany = AsyncMock()
        conn.commit = AsyncMock()
        db = Database("postgresql://user@localhost/x")
        db._conn = conn
        db._in_transaction = True
        await db.executemany("INSERT INTO t VALUES (?)", [[1]])
        conn.commit.assert_not_awaited()


class TestPostgresInsert:
    def _pg_db(self, fetch_results, dialect="postgresql"):
        db = Database("postgresql://user@localhost/x")
        db._dialect = dialect
        db._conn = MagicMock()
        db._in_transaction = False
        db.fetch_one = AsyncMock(side_effect=fetch_results)
        db.execute = AsyncMock(return_value=99)
        return db

    def _model(self):
        class M(Model):
            __tablename__ = "pg_t"
            id = fields.Integer(primary_key=True)
            name = fields.String(max_length=50)

        return M

    @pytest.mark.anyio
    async def test_insert_returning_sets_pk(self):
        M = self._model()
        db = self._pg_db([{"id": 7}])
        inst = M(name="A")
        inst._db = db
        await inst._insert()
        assert inst.id == 7
        sql = db.fetch_one.await_args.args[0]
        assert "RETURNING id" in sql

    @pytest.mark.anyio
    async def test_insert_returning_empty_result(self):
        M = self._model()
        db = self._pg_db([{}])
        inst = M(name="A")
        inst._db = db
        await inst._insert()
        assert inst.id is None

    @pytest.mark.anyio
    async def test_insert_sqlite_with_explicit_pk(self):
        class M(Model):
            __tablename__ = "pk_set"
            id = fields.Integer(primary_key=True)
            name = fields.String(max_length=50)

        db = Database("sqlite:///:memory:")
        db.register_model(M)
        await db.create_all()

        inst = M(id=42, name="A")
        inst._db = db
        await inst.save()
        assert inst.id == 42
        await db.disconnect()

    @pytest.mark.anyio
    async def test_insert_oracle_with_explicit_pk(self):
        M = self._model()
        db = self._pg_db([], dialect="oracle")
        inst = M(id=5, name="A")
        inst._db = db
        await inst._insert()
        assert inst.id == 5
        assert db.fetch_one.await_count == 0

    @pytest.mark.anyio
    async def test_insert_oracle_fallback_no_result(self):
        M = self._model()
        db = self._pg_db([None], dialect="oracle")
        inst = M(name="A")
        inst._db = db
        await inst._insert()
        assert inst.id is None

    @pytest.mark.anyio
    async def test_insert_returning_missing_falls_back(self):
        M = self._model()
        db = self._pg_db([{"id": 8}], dialect="oracle")
        inst = M(name="A")
        inst._db = db
        await inst._insert()
        assert inst.id == 8
        assert db.fetch_one.await_count == 1
        assert db.execute.await_args.args[0].startswith("INSERT INTO pg_t")

    @pytest.mark.anyio
    async def test_insert_returning_error_swallowed(self):
        M = self._model()
        db = self._pg_db([RuntimeError("nope")], dialect="oracle")
        inst = M(name="A")
        inst._db = db
        await inst._insert()
        assert inst.id is None
