import httpx
from typing import Any

class FenrirTestClient:
    __test__ = False

    def __init__(self, app: Any, follow_redirects: bool = False):
        self.app = app
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            follow_redirects=follow_redirects,
        )

    async def __aenter__(self) -> "FenrirTestClient":
        await self.client.__aenter__()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any):
        await self.client.__aexit__(exc_type, exc_val, exc_tb)

    async def request(self, method: str, url: str, *args: Any, **kwargs: Any) -> httpx.Response:
        return await self.client.request(method, url, *args, **kwargs)

    async def get(self, *args: Any, **kwargs: Any) -> httpx.Response:
        return await self.client.get(*args, **kwargs)

    async def post(self, *args: Any, **kwargs: Any) -> httpx.Response:
        return await self.client.post(*args, **kwargs)

    async def put(self, *args: Any, **kwargs: Any) -> httpx.Response:
        return await self.client.put(*args, **kwargs)

    async def delete(self, *args: Any, **kwargs: Any) -> httpx.Response:
        return await self.client.delete(*args, **kwargs)

    async def patch(self, *args: Any, **kwargs: Any) -> httpx.Response:
        return await self.client.patch(*args, **kwargs)

    async def options(self, *args: Any, **kwargs: Any) -> httpx.Response:
        return await self.client.options(*args, **kwargs)

    async def head(self, *args: Any, **kwargs: Any) -> httpx.Response:
        return await self.client.head(*args, **kwargs)


TestClient = FenrirTestClient
