import asyncio
from typing import Any

class UploadFile:
    def __init__(self, filename: str, file_object: Any, content_type: str = ""):
        self.filename = filename
        self.file = file_object
        self.content_type = content_type

    async def read(self, size: int = -1) -> bytes:
        if asyncio.iscoroutinefunction(self.file.read):
            return await self.file.read(size)
        return self.file.read(size)

    async def write(self, data: bytes):
        if asyncio.iscoroutinefunction(self.file.write):
            await self.file.write(data)
        else:
            self.file.write(data)

    async def seek(self, offset: int):
        if asyncio.iscoroutinefunction(self.file.seek):
            await self.file.seek(offset)
        else:
            self.file.seek(offset)

    async def close(self):
        if hasattr(self.file, "close"):
            if asyncio.iscoroutinefunction(self.file.close):
                await self.file.close()
            else:
                self.file.close()
