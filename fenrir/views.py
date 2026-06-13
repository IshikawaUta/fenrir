import inspect
from typing import Any, List, Optional

class View:
    methods: Optional[List[str]] = None
    provide_automatic_options: Optional[bool] = None

    def dispatch_request(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError()

    @classmethod
    def as_view(cls, name: str, *class_args: Any, **class_kwargs: Any):
        async def view(*args: Any, **kwargs: Any) -> Any:
            self = cls(*class_args, **class_kwargs)
            res = self.dispatch_request(*args, **kwargs)
            if inspect.isawaitable(res):
                return await res
            return res

        view.__name__ = name
        view.__doc__ = cls.__doc__
        view.__module__ = cls.__module__
        
        methods = cls.methods
        if methods is None:
            methods = []
            for m in ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"]:
                if hasattr(cls, m.lower()) and callable(getattr(cls, m.lower())):
                    methods.append(m)
            if not methods:
                methods = ["GET"]

        view.methods = methods
        view.provide_automatic_options = cls.provide_automatic_options
        return view


class MethodView(View):
    async def dispatch_request(self, *args: Any, **kwargs: Any) -> Any:
        from fenrir.context import _request_ctx_var, _app_ctx_var
        from fenrir.dependencies import resolve_parameters

        # Get request from the ASGI context
        try:
            req = _request_ctx_var.get()
        except LookupError:
            req = None

        method = (req.method if req else "GET") or "GET"
        method = method.upper()
        meth = getattr(self, method.lower(), None)
        if meth is None and method == "HEAD":
            meth = getattr(self, "get", None)
        if meth is None and method == "OPTIONS":
            allowed = []
            for m in ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"]:
                if hasattr(self, m.lower()) and callable(getattr(self, m.lower())):
                    allowed.append(m)
            if "GET" in allowed and "HEAD" not in allowed:
                allowed.append("HEAD")
            if "OPTIONS" not in allowed:
                allowed.append("OPTIONS")
            from fenrir.response import Response
            return Response(b"", status=200, headers={"allow": ", ".join(sorted(allowed))})
        if meth is None:
            raise RuntimeError(f"Unimplemented method {method!r}")

        if req is not None:
            # Get app from context to access router for path param extraction
            try:
                app = _app_ctx_var.get()
            except LookupError:
                app = None

            path_params = getattr(req, "path_params", {})

            from fenrir.response import Response as _Resp
            resp = _Resp()
            resolved = await resolve_parameters(meth, path_params, req, resp)
            res = meth(**resolved)
        else:
            res = meth(**kwargs)

        if inspect.isawaitable(res):
            return await res
        return res
