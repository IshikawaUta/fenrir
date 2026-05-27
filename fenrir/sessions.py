from itsdangerous import URLSafeTimedSerializer, BadSignature
from typing import Any, Optional

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
        res = super().pop(key, default)
        self.modified = True
        return res

    def update(self, *args: Any, **kwargs: Any):
        super().update(*args, **kwargs)
        self.modified = True


class SecureCookieSession(SessionMixin):
    pass


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
            # SECRET_KEY is missing, can't sign/save session
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
