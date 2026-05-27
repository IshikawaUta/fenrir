"""
fenrir.background — BackgroundTasks support.

Allows route handlers to schedule work that runs *after* the HTTP response
has already been sent to the client, without blocking the response.

Usage::

    from fenrir import Fenrir, BackgroundTasks

    app = Fenrir()

    def send_email(to: str):
        ...  # slow I/O

    @app.post("/notify")
    async def notify(tasks: BackgroundTasks):
        tasks.add_task(send_email, to="user@example.com")
        return {"status": "queued"}
"""
from __future__ import annotations

import asyncio
import inspect
import logging
from typing import Any, Callable, List

logger = logging.getLogger("fenrir.background")


class BackgroundTask:
    """A single task to run in the background."""

    def __init__(self, func: Callable, *args: Any, **kwargs: Any) -> None:
        self.func = func
        self.args = args
        self.kwargs = kwargs

    async def __call__(self) -> None:
        try:
            if inspect.iscoroutinefunction(self.func):
                await self.func(*self.args, **self.kwargs)
            else:
                await asyncio.to_thread(self.func, *self.args, **self.kwargs)
        except Exception:
            logger.exception("Error in background task %r", self.func)


class BackgroundTasks:
    """A collection of tasks to be executed after the response is sent.

    Inject via type annotation in route handlers::

        @app.get("/")
        async def index(tasks: BackgroundTasks):
            tasks.add_task(my_func, arg1, key=value)
            return "ok"
    """

    def __init__(self, tasks: List[BackgroundTask] = None) -> None:
        self.tasks: List[BackgroundTask] = tasks or []

    def add_task(self, func: Callable, *args: Any, **kwargs: Any) -> None:
        """Schedule *func* to run after the response is sent."""
        self.tasks.append(BackgroundTask(func, *args, **kwargs))

    async def __call__(self) -> None:
        """Run all scheduled tasks sequentially."""
        for task in self.tasks:
            await task()
