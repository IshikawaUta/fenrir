"""Coverage tests for fenrir.sessions."""
import sys
import types

import pytest

from fenrir.sessions import (
    InMemorySessionBackend,
    InMemorySessionInterface,
    RedisSessionInterface,
    SecureCookieSession,
    SecureCookieSessionInterface,
    ServerSideSession,
)


class _App:
    config = {}


class _Req:
    def __init__(self, cookies=None):
        self.cookies = cookies or {}


class _Resp:
    def __init__(self):
        self.cookies_set = []
        self.cookies_del = []

    def set_cookie(self, *args, **kwargs):
        self.cookies_set.append((args, kwargs))

    def delete_cookie(self, *args, **kwargs):
        self.cookies_del.append((args, kwargs))


def _session_config(**extra):
    cfg = {
        "SESSION_COOKIE_NAME": "session",
        "SESSION_COOKIE_PATH": "/",
        "SESSION_COOKIE_DOMAIN": None,
    }
    cfg.update(extra)
    return cfg


# ─────────────────────────── SecureCookie ───────────────────────────

def test_secure_cookie_open_no_secret():
    app = _App()
    app.config = _session_config()
    s = SecureCookieSessionInterface().open_session(app, _Req())
    assert isinstance(s, SecureCookieSession)
    assert len(s) == 0


def test_secure_cookie_save_none_session():
    iface = SecureCookieSessionInterface()
    resp = _Resp()
    iface.save_session(_App(), None, resp)
    assert resp.cookies_set == []
    assert resp.cookies_del == []


def test_secure_cookie_save_no_secret():
    app = _App()
    app.config = _session_config()
    resp = _Resp()
    SecureCookieSessionInterface().save_session(app, SecureCookieSession({"a": 1}), resp)
    assert resp.cookies_set == []


def test_secure_cookie_save_empty_modified():
    app = _App()
    app.config = _session_config()
    app.config["SECRET_KEY"] = "secret"
    s = SecureCookieSession()
    s.modified = True
    resp = _Resp()
    SecureCookieSessionInterface().save_session(app, s, resp)
    assert len(resp.cookies_del) == 1


def test_secure_cookie_bad_signature():
    app = _App()
    app.config = _session_config()
    app.config["SECRET_KEY"] = "secret"
    iface = SecureCookieSessionInterface()
    s = iface.open_session(app, _Req({"session": "not-a-valid-signature"}))
    assert isinstance(s, SecureCookieSession)
    assert len(s) == 0


def test_secure_cookie_bad_signature_import_fallback(monkeypatch):
    from itsdangerous import URLSafeTimedSerializer

    fake = types.ModuleType("itsdangerous")
    fake.URLSafeTimedSerializer = URLSafeTimedSerializer
    monkeypatch.setitem(sys.modules, "itsdangerous", fake)

    app = _App()
    app.config = _session_config()
    app.config["SECRET_KEY"] = "secret"
    iface = SecureCookieSessionInterface()
    s = iface.open_session(app, _Req({"session": "garbage"}))
    assert len(s) == 0


def test_secure_cookie_roundtrip():
    app = _App()
    app.config = _session_config()
    app.config["SECRET_KEY"] = "secret"
    iface = SecureCookieSessionInterface()

    resp = _Resp()
    iface.save_session(app, SecureCookieSession({"user": "u"}), resp)
    val = resp.cookies_set[0][0][1]

    s2 = iface.open_session(app, _Req({"session": val}))
    assert s2["user"] == "u"


def test_session_mixin_mutations():
    s = SecureCookieSession({"a": 1, "b": 2})
    assert s.modified is False
    del s["a"]
    assert s.modified is True

    s.modified = False
    s.clear()
    assert s.modified is True

    s["x"] = 1
    s.modified = False
    s.pop("x")
    assert s.modified is True
    s.modified = False
    s.pop("missing")
    assert s.modified is False

    s.update({"y": 2})
    assert s.modified is True


def test_secure_cookie_save_empty_not_modified():
    app = _App()
    app.config = _session_config()
    app.config["SECRET_KEY"] = "secret"
    resp = _Resp()
    SecureCookieSessionInterface().save_session(app, SecureCookieSession(), resp)
    assert resp.cookies_del == []


# ────────────────────────────── Redis ───────────────────────────────

def test_redis_requires_client():
    iface = RedisSessionInterface()
    with pytest.raises(ImportError, match="redis client"):
        iface._get_redis(None)


def test_run_sync_or_async_sync_value():
    assert RedisSessionInterface()._run_sync_or_async(42) == 42


@pytest.mark.anyio
async def test_run_sync_or_async_running_loop():
    iface = RedisSessionInterface()

    async def coro():
        return 1

    c = coro()
    # F9 fix: Instead of raising RuntimeError, we now run via ThreadPoolExecutor
    result = iface._run_sync_or_async(c)
    assert result == 1


def test_run_sync_or_async_new_loop():
    iface = RedisSessionInterface()

    async def coro():
        return 7

    assert iface._run_sync_or_async(coro()) == 7


def test_redis_open_session_with_bytes_data():
    class _Redis:
        def get(self, key):
            return b'{"user": "alice"}'

    app = _App()
    app.config = _session_config()
    iface = RedisSessionInterface(redis_client=_Redis())
    s = iface.open_session(app, _Req({"session": "sess1"}))
    assert s["user"] == "alice"
    assert s.sid == "sess1"


def test_redis_open_session_with_dict_data():
    class _Redis:
        def get(self, key):
            return {"user": "bob"}

    app = _App()
    app.config = _session_config()
    iface = RedisSessionInterface(redis_client=_Redis())
    s = iface.open_session(app, _Req({"session": "s1"}))
    assert s["user"] == "bob"


def test_redis_open_session_error():
    class _Redis:
        def get(self, key):
            raise ConnectionError("down")

    app = _App()
    app.config = _session_config()
    iface = RedisSessionInterface(redis_client=_Redis())
    s = iface.open_session(app, _Req({"session": "s1"}))
    assert s.sid == "s1"
    assert len(s) == 0


def test_redis_open_session_new_sid():
    class _Redis:
        def get(self, key):
            return None

    app = _App()
    app.config = _session_config()
    iface = RedisSessionInterface(redis_client=_Redis())
    s = iface.open_session(app, _Req())
    assert s.sid


def test_redis_open_session_invalid_json():
    class _Redis:
        def get(self, key):
            return b"not-json"

    app = _App()
    app.config = _session_config()
    iface = RedisSessionInterface(redis_client=_Redis())
    s = iface.open_session(app, _Req({"session": "s1"}))
    assert len(s) == 0
    assert s.sid == "s1"


def test_redis_save_non_server_session():
    iface = RedisSessionInterface(redis_client=object())
    resp = _Resp()
    iface.save_session(_App(), SecureCookieSession({"a": 1}), resp)
    assert resp.cookies_set == []


def test_redis_save_empty_delete():
    class _Redis:
        def delete(self, key):
            return "ok"

    app = _App()
    app.config = _session_config()
    iface = RedisSessionInterface(redis_client=_Redis())
    s = ServerSideSession()
    s.sid = "s1"
    resp = _Resp()
    iface.save_session(app, s, resp)
    assert len(resp.cookies_del) == 1


def test_redis_save_empty_delete_error():
    class _Redis:
        def delete(self, key):
            raise ConnectionError("down")

    app = _App()
    app.config = _session_config()
    iface = RedisSessionInterface(redis_client=_Redis())
    s = ServerSideSession()
    s.sid = "s1"
    resp = _Resp()
    iface.save_session(app, s, resp)
    assert len(resp.cookies_del) == 1


def test_redis_save_set():
    class _Redis:
        def set(self, key, value, ex=None):
            return "ok"

    app = _App()
    app.config = _session_config()
    iface = RedisSessionInterface(redis_client=_Redis())
    s = ServerSideSession({"a": 1})
    s.sid = "s1"
    resp = _Resp()
    iface.save_session(app, s, resp)
    assert resp.cookies_set[0][0][1] == "s1"


def test_redis_save_set_error():
    class _Redis:
        def set(self, key, value, ex=None):
            raise ConnectionError("down")

    app = _App()
    app.config = _session_config()
    iface = RedisSessionInterface(redis_client=_Redis())
    s = ServerSideSession({"a": 1})
    s.sid = "s1"
    resp = _Resp()
    iface.save_session(app, s, resp)
    assert len(resp.cookies_set) == 1


# ─────────────────────────── In-Memory ──────────────────────────────

def test_inmemory_backend_get_delete():
    backend = InMemorySessionBackend()
    assert backend.get("nope") is None
    backend.set("a", {"v": 1})
    assert backend.get("a") == {"v": 1}
    backend.delete("a")
    assert backend.get("a") is None


def test_inmemory_backend_cleanup():
    backend = InMemorySessionBackend()
    backend.set("old", {"x": 1}, ttl=-10)
    backend.set("new", {"y": 2}, ttl=100)
    backend.cleanup()
    assert "old" not in backend._store
    assert "new" in backend._store


def test_inmemory_open_session_existing():
    backend = InMemorySessionBackend()
    backend.set("s1", {"user": "carol"})
    app = _App()
    app.config = _session_config()
    iface = InMemorySessionInterface(backend=backend)
    s = iface.open_session(app, _Req({"session": "s1"}))
    assert s["user"] == "carol"
    assert s.sid == "s1"


def test_inmemory_open_session_new():
    app = _App()
    app.config = _session_config()
    s = InMemorySessionInterface().open_session(app, _Req())
    assert s.sid


def test_inmemory_open_session_sid_no_data():
    app = _App()
    app.config = _session_config()
    s = InMemorySessionInterface().open_session(app, _Req({"session": "unknown"}))
    assert s.sid == "unknown"
    assert len(s) == 0


def test_inmemory_save_non_server():
    iface = InMemorySessionInterface()
    resp = _Resp()
    iface.save_session(_App(), SecureCookieSession({"a": 1}), resp)
    assert resp.cookies_set == []


def test_inmemory_save_empty_delete():
    app = _App()
    app.config = _session_config()
    iface = InMemorySessionInterface()
    s = ServerSideSession()
    s.sid = "s1"
    resp = _Resp()
    iface.save_session(app, s, resp)
    assert len(resp.cookies_del) == 1


def test_inmemory_save_set():
    app = _App()
    app.config = _session_config()
    iface = InMemorySessionInterface()
    s = ServerSideSession({"a": 1})
    s.sid = "s1"
    resp = _Resp()
    iface.save_session(app, s, resp)
    assert resp.cookies_set[0][0][1] == "s1"
