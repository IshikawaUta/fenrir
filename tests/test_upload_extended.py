"""Tests for fenrir.upload module."""
import io

import pytest

from fenrir.upload import UploadFile

# ═══════════════════════════════════════════════════════════════════════
# UploadFile with Sync File Object
# ═══════════════════════════════════════════════════════════════════════

class TestUploadFileSyncFile:
    def test_init(self):
        buf = io.BytesIO(b"hello")
        uf = UploadFile("test.txt", buf, "text/plain")
        assert uf.filename == "test.txt"
        assert uf.file is buf
        assert uf.content_type == "text/plain"

    def test_init_default_content_type(self):
        uf = UploadFile("test.txt", io.BytesIO())
        assert uf.content_type == ""

    @pytest.mark.anyio
    async def test_read_sync(self):
        buf = io.BytesIO(b"hello world")
        uf = UploadFile("test.txt", buf)
        result = await uf.read()
        assert result == b"hello world"

    @pytest.mark.anyio
    async def test_read_sync_with_size(self):
        buf = io.BytesIO(b"hello world")
        uf = UploadFile("test.txt", buf)
        result = await uf.read(5)
        assert result == b"hello"

    @pytest.mark.anyio
    async def test_write_sync(self):
        buf = io.BytesIO()
        uf = UploadFile("test.txt", buf)
        await uf.write(b"data")
        buf.seek(0)
        assert buf.read() == b"data"

    @pytest.mark.anyio
    async def test_seek_sync(self):
        buf = io.BytesIO(b"hello")
        uf = UploadFile("test.txt", buf)
        await uf.read()
        await uf.seek(0)
        result = await uf.read()
        assert result == b"hello"

    @pytest.mark.anyio
    async def test_close_sync(self):
        buf = io.BytesIO()
        uf = UploadFile("test.txt", buf)
        await uf.close()
        assert buf.closed


# ═══════════════════════════════════════════════════════════════════════
# UploadFile with Async File Object
# ═══════════════════════════════════════════════════════════════════════

class MockAsyncFile:
    def __init__(self, data: bytes = b""):
        self._data = data
        self._pos = 0
        self.closed = False

    async def read(self, size=-1):
        if size == -1:
            result = self._data[self._pos:]
            self._pos = len(self._data)
        else:
            result = self._data[self._pos:self._pos + size]
            self._pos += len(result)
        return result

    async def write(self, data):
        self._data = self._data[:self._pos] + data + self._data[self._pos + len(data):]
        self._pos += len(data)

    async def seek(self, offset):
        self._pos = offset

    async def close(self):
        self.closed = True


class TestUploadFileAsyncFile:
    @pytest.mark.anyio
    async def test_read_async(self):
        f = MockAsyncFile(b"hello async")
        uf = UploadFile("test.txt", f)
        result = await uf.read()
        assert result == b"hello async"

    @pytest.mark.anyio
    async def test_read_async_with_size(self):
        f = MockAsyncFile(b"hello async")
        uf = UploadFile("test.txt", f)
        result = await uf.read(5)
        assert result == b"hello"

    @pytest.mark.anyio
    async def test_write_async(self):
        f = MockAsyncFile()
        uf = UploadFile("test.txt", f)
        await uf.write(b"data")
        assert f._data[:4] == b"data"

    @pytest.mark.anyio
    async def test_seek_async(self):
        f = MockAsyncFile(b"hello")
        uf = UploadFile("test.txt", f)
        await uf.read()
        await uf.seek(0)
        result = await uf.read()
        assert result == b"hello"

    @pytest.mark.anyio
    async def test_close_async(self):
        f = MockAsyncFile()
        uf = UploadFile("test.txt", f)
        await uf.close()
        assert f.closed is True


# ═══════════════════════════════════════════════════════════════════════
# UploadFile Edge Cases
# ═══════════════════════════════════════════════════════════════════════

class TestUploadFileEdgeCases:
    @pytest.mark.anyio
    async def test_close_no_close_method(self):
        class NoCloseFile:
            async def read(self, size=-1):
                return b""
            async def write(self, data):
                pass
        uf = UploadFile("test.txt", NoCloseFile())
        await uf.close()  # Should not raise

    @pytest.mark.anyio
    async def test_read_empty_sync(self):
        buf = io.BytesIO()
        uf = UploadFile("test.txt", buf)
        result = await uf.read()
        assert result == b""

    @pytest.mark.anyio
    async def test_write_then_read_sync(self):
        buf = io.BytesIO()
        uf = UploadFile("test.txt", buf)
        await uf.write(b"hello")
        await uf.seek(0)
        result = await uf.read()
        assert result == b"hello"

    @pytest.mark.anyio
    async def test_multiple_read_sync(self):
        buf = io.BytesIO(b"abcdefgh")
        uf = UploadFile("test.txt", buf)
        r1 = await uf.read(3)
        r2 = await uf.read(3)
        r3 = await uf.read()
        assert r1 == b"abc"
        assert r2 == b"def"
        assert r3 == b"gh"
