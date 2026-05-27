import os
import sys
from typing import Any
from fenrir.exceptions import HTTPInternalServerError

class BaseTemplateRenderer:
    def render(self, template_name: str, **context: Any) -> str:
        raise NotImplementedError("Renderer must implement render()")


class Jinja2Renderer(BaseTemplateRenderer):
    def __init__(self, template_folder: str = "templates"):
        try:
            from jinja2 import Environment, FileSystemLoader
        except ImportError:
            raise ImportError("Jinja2 is required to use Jinja2Renderer. Install it with: pip install jinja2")

        if not os.path.isabs(template_folder):
            template_folder = os.path.abspath(template_folder)
        os.makedirs(template_folder, exist_ok=True)
        self.env = Environment(
            loader=FileSystemLoader(template_folder),
            autoescape=True
        )

    def render(self, template_name: str, **context: Any) -> str:
        template = self.env.get_template(template_name)
        return template.render(**context)


def render_template(template_name: str, **context: Any) -> str:
    """Render a template using the active app's renderer (Flask style)."""
    from fenrir.app import _active_app
    from fenrir.signals import template_rendered

    # Try to find active app from global context or sys namespace
    app = _active_app or getattr(sys, "_fenrir_active_app", None)

    if app is not None and hasattr(app, "renderer") and app.renderer is not None:
        try:
            rendered = app.renderer.render(template_name, **context)
            template_rendered.send(app, template=template_name, context=context)
            return rendered
        except Exception as e:
            raise HTTPInternalServerError(detail=f"Template rendering failed: {e}")

    # Fallback to a default Jinja2Renderer if no active app is configured
    try:
        renderer = Jinja2Renderer("templates")
        rendered = renderer.render(template_name, **context)
        if app is not None:
            template_rendered.send(app, template=template_name, context=context)
        return rendered
    except Exception as e:
        raise HTTPInternalServerError(detail=f"Template rendering failed: {e}")
