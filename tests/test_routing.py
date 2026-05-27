import pytest
import httpx
from fenrir import Fenrir, Response

@pytest.mark.anyio
async def test_basic_routing():
    app = Fenrir()
    
    @app.get("/hello")
    async def hello():
        return "Hello World"
        
    @app.post("/submit")
    async def submit():
        return {"status": "ok"}
        
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/hello")
        assert res.status_code == 200
        assert res.text == "Hello World"
        
        res_post = await client.post("/submit")
        assert res_post.status_code == 200
        assert res_post.json() == {"status": "ok"}


@pytest.mark.anyio
async def test_path_parameters():
    app = Fenrir()
    
    # Bottle style syntax
    @app.get("/users/<user_id:int>")
    async def get_user(user_id: int):
        return {"user_id": user_id}
        
    # Flask style syntax
    @app.get("/posts/<int:post_id>")
    async def get_post(post_id: int):
        return {"post_id": post_id}
        
    # Float and regex
    @app.get("/items/<price:float>")
    async def get_item_price(price: float):
        return {"price": price}
        
    @app.get("/regex/<re:[a-z]{3}:code>")
    async def get_regex(code: str):
        return {"code": code}

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/users/123")
        assert res.status_code == 200
        assert res.json() == {"user_id": 123}
        
        # Should be 404 since it expects integer
        res = await client.get("/users/abc")
        assert res.status_code == 404
        
        res = await client.get("/posts/456")
        assert res.status_code == 200
        assert res.json() == {"post_id": 456}
        
        res = await client.get("/items/12.34")
        assert res.status_code == 200
        assert res.json() == {"price": 12.34}
        
        res = await client.get("/regex/abc")
        assert res.status_code == 200
        assert res.json() == {"code": "abc"}
        
        res = await client.get("/regex/abcd")
        assert res.status_code == 404
