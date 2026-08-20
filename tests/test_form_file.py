import httpx
import pytest

from fenrir import Fenrir, File, Form
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


@pytest.mark.anyio
async def test_multipart_duplicate_fields():
    app = Fenrir()

    @app.post("/multi")
    async def multi(tag=Form()):
        return {"tags": tag}

    body = (
        b"--b\r\n"
        b'Content-Disposition: form-data; name="tag"\r\n\r\n'
        b"a\r\n"
        b"--b\r\n"
        b'Content-Disposition: form-data; name="tag"\r\n\r\n'
        b"b\r\n"
        b"--b\r\n"
        b'Content-Disposition: form-data; name="tag"\r\n\r\n'
        b"c\r\n"
        b"--b--\r\n"
    )

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post("/multi", content=body, headers={"Content-Type": "multipart/form-data; boundary=b"})
        assert res.status_code == 200
        assert res.json()["tags"] == ["a", "b", "c"]


@pytest.mark.anyio
async def test_multipart_duplicate_files():
    app = Fenrir()

    @app.post("/up2")
    async def up2(f=File()):
        names = [x.filename for x in f] if isinstance(f, list) else [f.filename]
        return {"names": names}

    body = (
        b"--b\r\n"
        b'Content-Disposition: form-data; name="f"; filename="a.txt"\r\n'
        b"Content-Type: text/plain\r\n\r\n"
        b"aaa\r\n"
        b"--b\r\n"
        b'Content-Disposition: form-data; name="f"; filename="b.txt"\r\n'
        b"Content-Type: text/plain\r\n\r\n"
        b"bbb\r\n"
        b"--b\r\n"
        b'Content-Disposition: form-data; name="f"; filename="c.txt"\r\n'
        b"Content-Type: text/plain\r\n\r\n"
        b"ccc\r\n"
        b"--b--\r\n"
    )

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post("/up2", content=body, headers={"Content-Type": "multipart/form-data; boundary=b"})
        assert res.status_code == 200
        assert res.json()["names"] == ["a.txt", "b.txt", "c.txt"]
