"""Fenrir application — re-exports from _app_core and _app_dispatch.

This module exists for backward compatibility.  The actual implementation
lives in ``_app_core`` (init, routing, middleware, blueprints) and
``_app_dispatch`` (ASGI dispatch, handler execution, response coercion).
"""
import sys
from typing import Optional

from fenrir._app_core import Blueprint, FenrirCoreMixin  # noqa: F401
from fenrir._app_dispatch import FenrirDispatchMixin

# Deprecated compatibility hook. The canonical way to access the active app is
# ``fenrir.context.current_app`` (backed by a contextvar). This attribute is
# only kept so existing imports/tests keep working; it is no longer written by
# the dispatch pipeline.
_active_app: Optional["Fenrir"] = None


def _get_active_app() -> Optional["Fenrir"]:
    """Return the app bound to the current contextvar, or None."""
    from fenrir.context import _app_ctx_var
    try:
        return _app_ctx_var.get()
    except LookupError:
        return None


class Fenrir(FenrirCoreMixin, FenrirDispatchMixin):
    """The Fenrir ASGI application class.

    Combines core functionality (routing, middleware, blueprints) with
    the ASGI dispatch pipeline (request handling, response coercion).
    """

    def __init__(self, **kwargs):
        self._init_core(**kwargs)

    def run(self, host: str = "127.0.0.1", port: int = 8000, workers: int = 1, app_path: Optional[str] = None, **kwargs):
        """Run the Fenrir app locally using Asteri ASGI worker."""
        import os

        from asteri.arbiter import Arbiter
        from asteri.workers.asgi import ASGIWorker

        if app_path is None:
            try:
                frame = sys._getframe(1)
                caller_file = frame.f_globals.get("__file__")
                caller_var = frame.f_locals.get("app")
                if caller_file and caller_var is self:
                    mod_name = frame.f_globals.get("__name__")
                    if mod_name and mod_name != "__main__":
                        app_path = f"{mod_name}:app"
                    else:
                        mod_path = os.path.splitext(os.path.relpath(caller_file))[0].replace(os.sep, ".")
                        app_path = f"{mod_path}:app"
            except Exception:
                pass

        if app_path is None:
            raise RuntimeError(
                "Could not auto-detect app_path. Pass it explicitly: "
                "app.run(app_path='myapp:app')"
            )

        arbiter = Arbiter(
            app_path=app_path,
            worker_class=ASGIWorker,
            num_workers=workers,
            binds=[f"{host}:{port}"],
            **kwargs,
        )
        try:
            arbiter.start()
        except KeyboardInterrupt:
            pass
