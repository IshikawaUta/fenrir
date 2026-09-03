import os
from typing import Any, Dict

from fenrir.exceptions import HTTPInternalServerError

_fallback_renderers: Dict[str, Any] = {}


def _get_fallback_renderer() -> Any:
    """Get (and cache) the default Jinja2 renderer for the current templates dir.

    Cached per resolved folder so repeated fallback renders reuse the same
    Jinja2 environment. Key includes CWD to avoid stale cache when working
    directory changes.
    """
    folder = os.path.abspath("templates")
    cache_key = os.path.join(os.getcwd(), folder)
    renderer = _fallback_renderers.get(cache_key)
    if renderer is None:
        renderer = Jinja2Renderer("templates")
        _fallback_renderers[cache_key] = renderer
    return renderer

class BaseTemplateRenderer:
    def render(self, template_name: str, **context: Any) -> str:
        raise NotImplementedError("Renderer must implement render()")


class Jinja2Renderer(BaseTemplateRenderer):
    def __init__(self, template_folder: str = "templates"):
        try:
            from jinja2 import Environment, FileSystemLoader
        except ImportError:
            raise ImportError("Jinja2 is required to use Jinja2Renderer. Install it with: pip install jinja2") from None

        if not os.path.isabs(template_folder):
            template_folder = os.path.abspath(template_folder)
        self.env = Environment(
            loader=FileSystemLoader(template_folder),
            autoescape=True
        )

    def render(self, template_name: str, **context: Any) -> str:
        template = self.env.get_template(template_name)
        return template.render(**context)


class LazyJinja2Renderer(BaseTemplateRenderer):
    """Defer the Jinja2 import and Environment creation until the first render.

    This keeps ``app.renderer`` usable (same ``render`` API, honours the
    configured template folder) while avoiding the ~20ms Jinja2 import cost
    during ``Fenrir()`` application construction.
    """

    def __init__(self, template_folder: str = "templates"):
        # Resolve to an absolute path eagerly (mirrors Jinja2Renderer) so the
        # folder is pinned at construction time even though the Jinja2 import
        # itself is deferred until the first render.
        if not os.path.isabs(template_folder):
            template_folder = os.path.abspath(template_folder)
        self.template_folder = template_folder
        self._renderer: Any = None

    def _get(self) -> Jinja2Renderer:
        if self._renderer is None:
            self._renderer = Jinja2Renderer(self.template_folder)
        return self._renderer

    def __getattr__(self, name: str) -> Any:
        return getattr(self._get(), name)

    def render(self, template_name: str, **context: Any) -> str:
        return self._get().render(template_name, **context)


def render_template(template_name: str, **context: Any) -> str:
    """Render a template using the active app's renderer (Flask style)."""
    from fenrir.app import _get_active_app
    from fenrir.signals import template_rendered

    app = _get_active_app()

    if app is not None and hasattr(app, "renderer") and app.renderer is not None:
        try:
            rendered = app.renderer.render(template_name, **context)
            template_rendered.send(app, template=template_name, context=context)
            return rendered
        except Exception as e:
            # Log the full error server-side but don't leak internal details to client
            import logging
            logging.getLogger("fenrir.templating").error(
                "Template rendering failed for '%s': %s", template_name, e
            )
            raise HTTPInternalServerError(detail="Template rendering failed") from e

    # Fallback to a default Jinja2Renderer if no active app is configured
    try:
        renderer = _get_fallback_renderer()
        rendered = renderer.render(template_name, **context)
        if app is not None:
            template_rendered.send(app, template=template_name, context=context)
        return rendered
    except Exception as e:
        import logging
        logging.getLogger("fenrir.templating").error(
            "Template rendering failed for '%s': %s", template_name, e
        )
        raise HTTPInternalServerError(detail="Template rendering failed") from e
