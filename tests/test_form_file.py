import pytest
import httpx
from fenrir import Fenrir, Form, File
from fenrir.upload import UploadFile

@pytest.mark.anyio
async def test_form_urlencoded():
    app = Fenrir()

    @app.post("/login")
    async def login(username: str = Form(), password: str = Form()):
        return {"username": username, "password": password}

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post("/login", data={"username": "alice", "password": "secretpassword"})
        assert res.status_code == 200
        assert res.json() == {"username": "alice", "password": "secretpassword"}


@pytest.mark.anyio
async def test_multipart_file_upload():
    app = Fenrir()

    @app.post("/upload")
    async def upload(
        note: str = Form(),
        file: UploadFile = File()
    ):
        content = await file.read()
        return {
            "note": note,
            "filename": file.filename,
            "content_type": file.content_type,
            "content": content.decode("utf-8")
        }

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        files = {"file": ("hello.txt", b"Hello Fenrir File", "text/plain")}
        data = {"note": "test upload"}
        res = await client.post("/upload", data=data, files=files)
        assert res.status_code == 200
        assert res.json() == {
            "note": "test upload",
            "filename": "hello.txt",
            "content_type": "text/plain",
            "content": "Hello Fenrir File"
        }
