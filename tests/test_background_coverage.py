"""Tests for fenrir.background — BackgroundTask and BackgroundTasks."""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock
from fenrir.background import BackgroundTask, BackgroundTasks


class TestBackgroundTask:
    def test_init_sync(self):
        def sync_func():
            pass
        task = BackgroundTask(sync_func, 1, 2, key="val")
        assert task.func is sync_func
        assert task.args == (1, 2)
        assert task.kwargs == {"key": "val"}
        assert task._is_async is False

    def test_init_async(self):
        async def async_func():
            pass
        task = BackgroundTask(async_func)
        assert task._is_async is True

    @pytest.mark.anyio
    async def test_call_async(self):
        called_with = []

        async def async_func(a, b):
            called_with.append((a, b))

        task = BackgroundTask(async_func, 1, 2)
        await task()
        assert called_with == [(1, 2)]

    @pytest.mark.anyio
    async def test_call_sync(self):
        called_with = []

        def sync_func(a, b):
            called_with.append((a, b))

        task = BackgroundTask(sync_func, 3, 4)
        await task()
        assert called_with == [(3, 4)]

    @pytest.mark.anyio
    async def test_call_exception_logged(self):
        def failing():
            raise RuntimeError("boom")

        task = BackgroundTask(failing)
        # Should not raise — exception is logged
        await task()

    @pytest.mark.anyio
    async def test_call_async_exception_logged(self):
        async def async_failing():
            raise RuntimeError("async boom")

        task = BackgroundTask(async_failing)
        await task()


class TestBackgroundTasks:
    def test_init_empty(self):
        bt = BackgroundTasks()
        assert bt.tasks == []

    def test_init_with_tasks(self):
        t1 = BackgroundTask(lambda: None)
        bt = BackgroundTasks([t1])
        assert len(bt.tasks) == 1

    def test_add_task(self):
        bt = BackgroundTasks()
        def my_func():
            pass
        bt.add_task(my_func, 1, key="val")
        assert len(bt.tasks) == 1
        assert bt.tasks[0].func is my_func
        assert bt.tasks[0].args == (1,)
        assert bt.tasks[0].kwargs == {"key": "val"}

    def test_add_multiple_tasks(self):
        bt = BackgroundTasks()
        bt.add_task(lambda: None)
        bt.add_task(lambda: None)
        assert len(bt.tasks) == 2

    @pytest.mark.anyio
    async def test_call_runs_all(self):
        results = []
        bt = BackgroundTasks()
        bt.add_task(lambda: results.append(1))
        bt.add_task(lambda: results.append(2))
        await bt()
        assert results == [1, 2]

    @pytest.mark.anyio
    async def test_call_empty(self):
        bt = BackgroundTasks()
        await bt()  # should not raise

    @pytest.mark.anyio
    async def test_call_with_async_tasks(self):
        results = []

        async def async_add(n):
            results.append(n)

        bt = BackgroundTasks()
        bt.add_task(async_add, 10)
        bt.add_task(async_add, 20)
        await bt()
        assert results == [10, 20]

    @pytest.mark.anyio
    async def test_call_mixed_sync_async(self):
        results = []

        def sync_add(n):
            results.append(n)

        async def async_add(n):
            results.append(n)

        bt = BackgroundTasks()
        bt.add_task(sync_add, 1)
        bt.add_task(async_add, 2)
        await bt()
        assert results == [1, 2]

    @pytest.mark.anyio
    async def test_call_exception_in_one_does_not_stop_others(self):
        results = []

        def failing():
            raise RuntimeError("fail")

        bt = BackgroundTasks()
        bt.add_task(failing)
        bt.add_task(lambda: results.append("after"))
        await bt()
        assert results == ["after"]
