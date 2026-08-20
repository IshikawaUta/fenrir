import contextvars
from typing import Any, Optional

_request_ctx_var: contextvars.ContextVar[Any] = contextvars.ContextVar("request_ctx")
_g_ctx_var: contextvars.ContextVar[Any] = contextvars.ContextVar("g_ctx")
_app_ctx_var: contextvars.ContextVar[Any] = contextvars.ContextVar("app_ctx")


class LocalProxy:
    def __init__(self, var: Any):
        object.__setattr__(self, "_var", var)

    def _get_current_object(self) -> Any:
        # If it's a contextvar, get its value.
        if isinstance(self._var, contextvars.ContextVar):
            try:
                return self._var.get()
            except LookupError:
                raise RuntimeError("Working outside of context.") from None
        # If it's callable, call it.
        elif callable(self._var):
            return self._var()
        raise RuntimeError("Unrecognized proxy target.")

    def __getattr__(self, name: str) -> Any:
        return getattr(self._get_current_object(), name)

    def __setattr__(self, name: str, value: Any):
        setattr(self._get_current_object(), name, value)

    def __delattr__(self, name: str):
        delattr(self._get_current_object(), name)

    def __repr__(self) -> str:
        try:
            return repr(self._get_current_object())
        except RuntimeError:
            return "<LocalProxy unbound>"

    def __getitem__(self, key: Any) -> Any:
        return self._get_current_object()[key]

    def __setitem__(self, key: Any, value: Any):
        self._get_current_object()[key] = value

    def __delitem__(self, key: Any):
        del self._get_current_object()[key]

    def __contains__(self, key: Any) -> bool:
        return key in self._get_current_object()

    def __len__(self) -> int:
        return len(self._get_current_object())

    def __iter__(self) -> Any:
        return iter(self._get_current_object())


class AppProxy(LocalProxy):
    def _get_current_object(self) -> Any:
        try:
            return _app_ctx_var.get()
        except LookupError:
            raise RuntimeError("Working outside of application context.") from None


class SessionProxy(LocalProxy):
    def _get_current_object(self) -> Any:
        try:
            req = _request_ctx_var.get()
            return req.session
        except LookupError:
            raise RuntimeError("Working outside of request context.") from None


class G:
    """A namespace object to store temporary data during a request."""
    def __repr__(self) -> str:
        return f"<g {self.__dict__}>"


request = LocalProxy(_request_ctx_var)
g = LocalProxy(_g_ctx_var)
current_app = AppProxy(None)
session = SessionProxy(None)


class AppContext:
    def __init__(self, app: Any):
        self.app = app
        self._token: Optional[contextvars.Token[Any]] = None

    def __enter__(self) -> "AppContext":
        self._token = _app_ctx_var.set(self.app)
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any):
        try:
            if hasattr(self.app, "do_teardown_appcontext"):
                self.app.do_teardown_appcontext(exc_val)
        finally:
            if self._token is not None:
                _app_ctx_var.reset(self._token)


class RequestContext:
    def __init__(self, app: Any, request_obj: Any):
        self.app = app
        self.request = request_obj
        self.app_ctx = AppContext(app)
        self._token_req: Optional[contextvars.Token[Any]] = None
        self._token_g: Optional[contextvars.Token[Any]] = None

    def __enter__(self) -> "RequestContext":
        self.app_ctx.__enter__()
        try:
            self._token_req = _request_ctx_var.set(self.request)
            self._token_g = _g_ctx_var.set(G())
        except Exception:
            self.app_ctx.__exit__(None, None, None)
            raise
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any):
        try:
            if hasattr(self.app, 'do_teardown_request'):
                self.app.do_teardown_request(exc_val)
        finally:
            if self._token_req is not None:
                _request_ctx_var.reset(self._token_req)
            if self._token_g is not None:
                _g_ctx_var.reset(self._token_g)
            self.app_ctx.__exit__(exc_type, exc_val, exc_tb)
