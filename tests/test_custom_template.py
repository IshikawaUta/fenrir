from typing import Any

import httpx
import pytest

from fenrir import Fenrir
from fenrir.templating import BaseTemplateRenderer, render_template


class CustomRenderer(BaseTemplateRenderer):
    def render(self, template_name: str, **context: Any) -> str:
        return f"Custom Template: {template_name} - value: {context.get('value')}"


@pytest.mark.anyio
async def test_custom_template_renderer():
    # Instantiate Fenrir with custom template renderer
    app = Fenrir(renderer=CustomRenderer())

    @app.get("/render")
    async def render_view():
        return render_template("home.html", value="1234")

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/render")
        assert res.status_code == 200
        assert res.text == "Custom Template: home.html - value: 1234"
