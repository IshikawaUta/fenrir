import json
import time
from itsdangerous import URLSafeTimedSerializer, BadSignature
from typing import Any, Dict, Optional


class SessionMixin(dict):
    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.modified = False
        self.accessed = False

    def __setitem__(self, key: Any, value: Any):
        super().__setitem__(key, value)
        self.modified = True

    def __delitem__(self, key: Any):
        super().__delitem__(key)
        self.modified = True

    def clear(self):
        super().clear()
        self.modified = True

    def pop(self, key: Any, default: Any = None) -> Any:
        if key in self:
            self.modified = True
        return super().pop(key, default)

    def update(self, *args: Any, **kwargs: Any):
        super().update(*args, **kwargs)
        self.modified = True


class SecureCookieSession(SessionMixin):
    pass


class ServerSideSession(SessionMixin):
    """A server-side session that tracks its session ID."""
    sid: str = ""


class SessionInterface:
    def open_session(self, app: Any, request: Any) -> Optional[SessionMixin]:
        raise NotImplementedError()

    def save_session(self, app: Any, session: SessionMixin, response: Any):
        raise NotImplementedError()


class SecureCookieSessionInterface(SessionInterface):
    salt = "cookie-session"

    def get_serializer(self, app: Any) -> Optional[URLSafeTimedSerializer]:
        secret_key = app.config.get("SECRET_KEY")
        if not secret_key:
            return None
        return URLSafeTimedSerializer(secret_key, salt=self.salt)

    def open_session(self, app: Any, request: Any) -> SecureCookieSession:
        serializer = self.get_serializer(app)
        if serializer is None:
            return SecureCookieSession()
        val = request.cookies.get(app.config.get("SESSION_COOKIE_NAME", "session"))
        if not val:
            return SecureCookieSession()
        try:
            data = serializer.loads(val)
            return SecureCookieSession(data)
        except BadSignature:
            return SecureCookieSession()

    def save_session(self, app: Any, session: SessionMixin, response: Any):
        name = app.config.get("SESSION_COOKIE_NAME", "session")
        domain = app.config.get("SESSION_COOKIE_DOMAIN")
        path = app.config.get("SESSION_COOKIE_PATH", "/")

        if session is None:
            return

        if not session:
            if session.modified:
                response.delete_cookie(name, domain=domain, path=path)
            return

        serializer = self.get_serializer(app)
        if serializer is None:
            return

        val = serializer.dumps(dict(session))
        response.set_cookie(
            name,
            val,
            path=path,
            domain=domain,
            secure=app.config.get("SESSION_COOKIE_SECURE", False),
            httponly=app.config.get("SESSION_COOKIE_HTTPONLY", True),
            samesite=app.config.get("SESSION_COOKIE_SAMESITE"),
        )


class RedisSessionInterface(SessionInterface):
    """Server-side session backed by Redis.

    Supports both sync (``fakeredis``, ``redis``) and async (``redis.asyncio``)
    redis clients.  When an async client is detected the coroutine is scheduled
    on the running event loop automatically.

    Config keys (set on ``app.config``):
        SESSION_COOKIE_NAME   - cookie name (default ``"session"``)
        SESSION_TTL           - session time-to-live in seconds (default 86400)
    """

    def __init__(self, redis_client: Any = None, prefix: str = "session:", ttl: int = 86400):
        self._redis = redis_client
        self.prefix = prefix
        self.ttl = ttl

    def _get_redis(self, app: Any) -> Any:
        if self._redis is not None:
            return self._redis
        raise ImportError(
            "RedisSessionInterface requires a redis client instance. "
            "Pass redis_client= to RedisSessionInterface."
        )

    def _generate_sid(self) -> str:
        return uuid4().hex

    @staticmethod
    def _run_sync_or_async(coro_or_value: Any) -> Any:
        """If *coro_or_value* is a coroutine, run it; otherwise return as-is."""
        import asyncio
        if asyncio.iscoroutine(coro_or_value):
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
            if loop and loop.is_running():
                import concurrent.futures
                future = concurrent.futures.Future()

                async def _wrapper():
                    try:
                        result = await coro_or_value
                        future.set_result(result)
                    except Exception as exc:
                        future.set_exception(exc)

                loop.create_task(_wrapper())
                try:
                    return future.result(timeout=5)
                except concurrent.futures.TimeoutError:
                    raise RuntimeError(
                        "Redis session operation timed out. "
                        "Ensure your Redis client supports sync operations "
                        "or use a sync redis client (e.g., redis-py synchronous)."
                    )
            else:
                return loop.run_until_complete(coro_or_value)
        return coro_or_value

    def open_session(self, app: Any, request: Any) -> ServerSideSession:
        name = app.config.get("SESSION_COOKIE_NAME", "session")
        sid = request.cookies.get(name)
        session = ServerSideSession()

        if sid:
            redis = self._get_redis(app)
            try:
                data = redis.get(self.prefix + sid)
                data = self._run_sync_or_async(data)
            except Exception:
                data = None

            if data:
                try:
                    if isinstance(data, (bytes, str)):
                        loaded = json.loads(data)
                    else:
                        loaded = data
                    session.update(loaded)
                except (json.JSONDecodeError, TypeError):
                    pass
            session.sid = sid
        else:
            session.sid = self._generate_sid()

        return session

    def save_session(self, app: Any, session: SessionMixin, response: Any):
        if session is None or not isinstance(session, ServerSideSession):
            return

        name = app.config.get("SESSION_COOKIE_NAME", "session")
        domain = app.config.get("SESSION_COOKIE_DOMAIN")
        path = app.config.get("SESSION_COOKIE_PATH", "/")
        ttl = app.config.get("SESSION_TTL", self.ttl)

        if not session:
            redis = self._get_redis(app)
            try:
                self._run_sync_or_async(redis.delete(self.prefix + session.sid))
            except Exception:
                pass
            response.delete_cookie(name, domain=domain, path=path)
            return

        redis = self._get_redis(app)
        data = json.dumps(dict(session))
        try:
            self._run_sync_or_async(redis.set(self.prefix + session.sid, data, ex=ttl))
        except Exception:
            pass

        response.set_cookie(
            name,
            session.sid,
            path=path,
            domain=domain,
            secure=app.config.get("SESSION_COOKIE_SECURE", False),
            httponly=app.config.get("SESSION_COOKIE_HTTPONLY", True),
            samesite=app.config.get("SESSION_COOKIE_SAMESITE"),
            max_age=ttl,
        )


class InMemorySessionBackend:
    """A simple in-memory session store for testing / single-process deployments."""

    def __init__(self):
        self._store: Dict[str, Dict[str, Any]] = {}
        self._expires: Dict[str, float] = {}

    def get(self, sid: str) -> Optional[Dict[str, Any]]:
        self._cleanup()
        return self._store.get(sid)

    def set(self, sid: str, data: Dict[str, Any], ttl: int = 86400) -> None:
        self._store[sid] = data
        self._expires[sid] = time.monotonic() + ttl

    def delete(self, sid: str) -> None:
        self._store.pop(sid, None)
        self._expires.pop(sid, None)

    def _cleanup(self) -> None:
        now = time.monotonic()
        expired = [k for k, exp in self._expires.items() if exp < now]
        for k in expired:
            self._store.pop(k, None)
            self._expires.pop(k, None)


class InMemorySessionInterface(SessionInterface):
    """Server-side session backed by an in-memory dict.

    Useful for testing and single-process deployments.
    """

    def __init__(self, backend: Optional[InMemorySessionBackend] = None, ttl: int = 86400):
        self.backend = backend or InMemorySessionBackend()
        self.ttl = ttl

    def open_session(self, app: Any, request: Any) -> ServerSideSession:
        import uuid as _uuid
        name = app.config.get("SESSION_COOKIE_NAME", "session")
        sid = request.cookies.get(name)
        session = ServerSideSession()

        if sid:
            data = self.backend.get(sid)
            if data:
                session.update(data)
            session.sid = sid
        else:
            session.sid = _uuid.uuid4().hex

        return session

    def save_session(self, app: Any, session: SessionMixin, response: Any):
        if session is None or not isinstance(session, ServerSideSession):
            return

        name = app.config.get("SESSION_COOKIE_NAME", "session")
        domain = app.config.get("SESSION_COOKIE_DOMAIN")
        path = app.config.get("SESSION_COOKIE_PATH", "/")
        ttl = app.config.get("SESSION_TTL", self.ttl)

        if not session:
            self.backend.delete(session.sid)
            response.delete_cookie(name, domain=domain, path=path)
            return

        self.backend.set(session.sid, dict(session), ttl)
        response.set_cookie(
            name,
            session.sid,
            path=path,
            domain=domain,
            secure=app.config.get("SESSION_COOKIE_SECURE", False),
            httponly=app.config.get("SESSION_COOKIE_HTTPONLY", True),
            samesite=app.config.get("SESSION_COOKIE_SAMESITE"),
            max_age=ttl,
        )


def uuid4() -> Any:
    import uuid
    return uuid.uuid4()
