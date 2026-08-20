"""Tests for fenrir.queue — MemoryQueue, Queue, Worker."""
import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from fenrir.queue import (
    Job,
    JobStatus,
    MemoryQueue,
    Queue,
    QueueBackend,
    Worker,
)


def _make_job(handler="test_handler", status=JobStatus.PENDING, priority=0, **kw):
    j = Job(handler=handler, **kw)
    j.status = status
    return j


# ═══════════════════════════════════════════════════════════════════════
# Job Tests
# ═══════════════════════════════════════════════════════════════════════

class TestJob:
    def test_from_dict_args_list_to_tuple(self):
        data = {"handler": "h", "args": [1, 2], "kwargs": {"a": 1}}
        j = Job.from_dict(data)
        assert isinstance(j.args, tuple)
        assert j.args == (1, 2)

    def test_from_dict_default_status(self):
        j = Job.from_dict({"handler": "h"})
        assert j.status == JobStatus.PENDING

    def test_to_dict_roundtrip(self):
        j = Job(handler="h", args=(1,), kwargs={"k": "v"})
        d = j.to_dict()
        j2 = Job.from_dict(d)
        assert j2.handler == "h"
        assert j2.args == (1,)
        assert j2.kwargs == {"k": "v"}


# ═══════════════════════════════════════════════════════════════════════
# QueueBackend Base Tests
# ═══════════════════════════════════════════════════════════════════════

class TestQueueBackend:
    @pytest.mark.anyio
    async def test_all_methods_raise(self):
        b = QueueBackend()
        with pytest.raises(NotImplementedError):
            await b.enqueue(MagicMock())
        with pytest.raises(NotImplementedError):
            await b.dequeue()
        with pytest.raises(NotImplementedError):
            await b.peek()
        with pytest.raises(NotImplementedError):
            await b.size()
        with pytest.raises(NotImplementedError):
            await b.requeue(MagicMock())
        with pytest.raises(NotImplementedError):
            await b.get_job("x")
        with pytest.raises(NotImplementedError):
            await b.update_job(MagicMock())
        with pytest.raises(NotImplementedError):
            await b.remove_job("x")
        with pytest.raises(NotImplementedError):
            await b.get_jobs_by_status(JobStatus.PENDING)


# ═══════════════════════════════════════════════════════════════════════
# MemoryQueue Tests
# ═══════════════════════════════════════════════════════════════════════

class TestMemoryQueue:
    @pytest.mark.anyio
    async def test_enqueue_dequeue(self):
        mq = MemoryQueue()
        job = _make_job()
        await mq.enqueue(job)
        result = await mq.dequeue()
        assert result.id == job.id
        assert result.status == JobStatus.PENDING

    @pytest.mark.anyio
    async def test_dequeue_empty(self):
        mq = MemoryQueue()
        result = await mq.dequeue()
        assert result is None

    @pytest.mark.anyio
    async def test_peek(self):
        mq = MemoryQueue()
        j1 = Job(handler="test_handler", priority=1)
        j2 = Job(handler="test_handler", priority=5)
        await mq.enqueue(j1)
        await mq.enqueue(j2)
        peeked = await mq.peek(2)
        assert len(peeked) == 2
        assert peeked[0].priority == 5

    @pytest.mark.anyio
    async def test_size(self):
        mq = MemoryQueue()
        await mq.enqueue(_make_job(status=JobStatus.PENDING))
        await mq.enqueue(_make_job(status=JobStatus.COMPLETED))
        assert await mq.size() == 1

    @pytest.mark.anyio
    async def test_requeue(self):
        mq = MemoryQueue()
        job = _make_job()
        await mq.enqueue(job)
        dequeued = await mq.dequeue()
        assert dequeued.id == job.id
        await mq.requeue(job)
        assert await mq.size() == 1

    @pytest.mark.anyio
    async def test_get_job(self):
        mq = MemoryQueue()
        job = _make_job()
        await mq.enqueue(job)
        found = await mq.get_job(job.id)
        assert found.id == job.id

    @pytest.mark.anyio
    async def test_get_job_not_found(self):
        mq = MemoryQueue()
        assert await mq.get_job("nonexistent") is None

    @pytest.mark.anyio
    async def test_update_job(self):
        mq = MemoryQueue()
        job = _make_job()
        await mq.enqueue(job)
        job.status = JobStatus.COMPLETED
        await mq.update_job(job)
        found = await mq.get_job(job.id)
        assert found.status == JobStatus.COMPLETED

    @pytest.mark.anyio
    async def test_remove_job(self):
        mq = MemoryQueue()
        job = _make_job()
        await mq.enqueue(job)
        assert await mq.remove_job(job.id) is True
        assert await mq.get_job(job.id) is None

    @pytest.mark.anyio
    async def test_remove_job_not_found(self):
        mq = MemoryQueue()
        assert await mq.remove_job("nonexistent") is False

    @pytest.mark.anyio
    async def test_get_jobs_by_status(self):
        mq = MemoryQueue()
        await mq.enqueue(_make_job(status=JobStatus.PENDING))
        await mq.enqueue(_make_job(status=JobStatus.FAILED))
        pending = await mq.get_jobs_by_status(JobStatus.PENDING)
        assert len(pending) == 1

    @pytest.mark.anyio
    async def test_dequeue_skips_cancelled(self):
        mq = MemoryQueue()
        j1 = _make_job()
        j1.status = JobStatus.CANCELLED
        j2 = _make_job()
        await mq.enqueue(j1)
        await mq.enqueue(j2)
        result = await mq.dequeue()
        assert result.id == j2.id

    @pytest.mark.anyio
    async def test_delayed_job_not_dequeued_before_ready(self):
        mq = MemoryQueue()
        job = Job(handler="test_handler", delay=0.1)
        await mq.enqueue(job)
        # Not ready yet — should not be dequeued
        assert await mq.dequeue() is None
        assert await mq.size() == 1
        # After the delay elapses it becomes available
        await asyncio.sleep(0.15)
        result = await mq.dequeue()
        assert result is not None
        assert result.id == job.id

    @pytest.mark.anyio
    async def test_requeue_delayed_job_honors_delay(self):
        mq = MemoryQueue()
        job = _make_job()
        await mq.enqueue(job)
        assert await mq.dequeue() is not None
        job.delay = 0.1
        await mq.requeue(job)
        assert await mq.dequeue() is None
        await asyncio.sleep(0.15)
        result = await mq.dequeue()
        assert result is not None


# ═══════════════════════════════════════════════════════════════════════
# Queue Tests
# ═══════════════════════════════════════════════════════════════════════

class TestQueue:
    def test_backend_property(self):
        mq = MemoryQueue()
        q = Queue(backend=mq)
        assert q.backend is mq

    def test_handler_decorator(self):
        q = Queue()

        @q.handler("my_job")
        async def my_job(x):
            return x

        assert "my_job" in q._handlers
        assert my_job._queue_name == "my_job"

    def test_register(self):
        q = Queue()
        q.register("manual", lambda x: x)
        assert "manual" in q._handlers

    @pytest.mark.anyio
    async def test_enqueue(self):
        q = Queue()
        job = await q.enqueue("test", 1, 2, key="val")
        assert job.handler == "test"
        assert job.args == (1, 2)
        assert job.kwargs == {"key": "val"}

    @pytest.mark.anyio
    async def test_process_next_no_handler(self):
        q = Queue()
        await q.enqueue("missing_handler")
        job = await q.process_next()
        assert job.status == JobStatus.FAILED
        assert "Handler not found" in job.error

    @pytest.mark.anyio
    async def test_process_next_sync_handler(self):
        q = Queue()
        q.register("sync_job", lambda x: x * 2)
        await q.enqueue("sync_job", 5)
        job = await q.process_next()
        assert job.status == JobStatus.COMPLETED
        assert job.result == 10

    @pytest.mark.anyio
    async def test_process_next_async_handler(self):
        q = Queue()

        @q.handler("async_job")
        async def async_job(x):
            return x + 1

        await q.enqueue("async_job", 9)
        job = await q.process_next()
        assert job.status == JobStatus.COMPLETED
        assert job.result == 10

    @pytest.mark.anyio
    async def test_process_next_timeout(self):
        q = Queue()

        @q.handler("slow")
        async def slow():
            await asyncio.sleep(10)

        await q.enqueue("slow", timeout=0.01)
        job = await q.process_next()
        assert job.status == JobStatus.FAILED
        assert "timed out" in job.error.lower()

    @pytest.mark.anyio
    async def test_process_next_retry(self):
        q = Queue()
        call_count = 0

        @q.handler("flaky")
        async def flaky():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise RuntimeError("transient error")
            return "ok"

        await q.enqueue("flaky", max_retries=3)
        job = await q.process_next()
        # After retry, job is requeued with PENDING status
        assert job.status == JobStatus.PENDING

    @pytest.mark.anyio
    async def test_process_next_permanent_fail(self):
        q = Queue()

        @q.handler("always_fail")
        async def always_fail():
            raise RuntimeError("permanent")

        await q.enqueue("always_fail", max_retries=0)
        job = await q.process_next()
        assert job.status == JobStatus.FAILED
        assert "permanent" in job.error

    @pytest.mark.anyio
    async def test_cancel(self):
        q = Queue()
        job = await q.enqueue("test")
        assert await q.cancel(job.id) is True
        # After cancel, remove_job is called, so job is removed
        found = await q.get_job(job.id)
        assert found is None

    @pytest.mark.anyio
    async def test_cancel_not_found(self):
        q = Queue()
        assert await q.cancel("nonexistent") is False

    @pytest.mark.anyio
    async def test_size(self):
        q = Queue()
        await q.enqueue("test")
        assert await q.size() == 1


# ═══════════════════════════════════════════════════════════════════════
# Worker Tests
# ═══════════════════════════════════════════════════════════════════════

class TestWorker:
    @pytest.mark.anyio
    async def test_start_stop(self):
        q = Queue()
        w = Worker(q, concurrency=1, poll_interval=0.01)
        await w.start()
        assert w._running is True
        assert len(w._tasks) == 1
        await w.stop()
        assert w._running is False

    @pytest.mark.anyio
    async def test_max_jobs(self):
        q = Queue()
        processed = []

        @q.handler("count")
        async def count():
            processed.append(1)

        for _ in range(3):
            await q.enqueue("count")

        w = Worker(q, concurrency=1, poll_interval=0.01, max_jobs=2)
        await w.run()
        assert w._jobs_processed == 2

    @pytest.mark.anyio
    async def test_worker_loop_exception(self):
        q = Queue()
        bad_backend = MagicMock()
        bad_backend.dequeue = AsyncMock(side_effect=RuntimeError("backend error"))
        q._backend = bad_backend
        w = Worker(q, concurrency=1, poll_interval=0.01, max_jobs=1)
        w._running = True
        # Run worker loop with timeout to avoid infinite loop
        try:
            await asyncio.wait_for(w._worker_loop(0), timeout=1.0)
        except asyncio.TimeoutError:
            pass
        # Should not crash


# ═══════════════════════════════════════════════════════════════════════
# Dead-letter & Persistence Tests
# ═══════════════════════════════════════════════════════════════════════

class TestDeadLetter:
    @pytest.mark.anyio
    async def test_dead_letter_handler_called_on_permanent_failure(self):
        q = Queue()
        dead_letters = []

        @q.handler("always_fail")
        async def always_fail():
            raise RuntimeError("permanent")

        q._dead_letter_handler = lambda job: dead_letters.append(job.id)

        await q.enqueue("always_fail", max_retries=0)
        job = await q.process_next()
        assert job.status == JobStatus.FAILED
        assert dead_letters == [job.id]

    @pytest.mark.anyio
    async def test_dead_letter_async_handler(self):
        q = Queue()
        dead_letters = []

        @q.handler("always_fail")
        async def always_fail():
            raise RuntimeError("permanent")

        async def handler(job):
            dead_letters.append(job.id)

        q._dead_letter_handler = handler

        await q.enqueue("always_fail", max_retries=0)
        job = await q.process_next()
        assert job.status == JobStatus.FAILED
        assert dead_letters == [job.id]

    @pytest.mark.anyio
    async def test_dead_letter_not_called_when_retry_succeeds(self):
        q = Queue(retry_backoff=0)
        dead_letters = []
        call_count = 0

        @q.handler("flaky")
        async def flaky():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("transient")
            return "ok"

        q._dead_letter_handler = lambda job: dead_letters.append(job.id)

        await q.enqueue("flaky", max_retries=1)
        first = await q.process_next()
        assert first.status == JobStatus.PENDING
        second = await q.process_next()
        assert second.status == JobStatus.COMPLETED
        assert dead_letters == []

    @pytest.mark.anyio
    async def test_dead_letter_handler_error_does_not_break_worker(self):
        q = Queue()

        @q.handler("always_fail")
        async def always_fail():
            raise RuntimeError("permanent")

        def handler(job):
            raise RuntimeError("handler bug")

        q._dead_letter_handler = handler

        await q.enqueue("always_fail", max_retries=0)
        job = await q.process_next()
        assert job.status == JobStatus.FAILED

    @pytest.mark.anyio
    async def test_dead_letter_not_called_without_handler(self):
        q = Queue()

        @q.handler("always_fail")
        async def always_fail():
            raise RuntimeError("permanent")

        await q.enqueue("always_fail", max_retries=0)
        job = await q.process_next()
        assert job.status == JobStatus.FAILED


class TestMemoryQueuePersistence:
    @pytest.mark.anyio
    async def test_jobs_survive_restart(self, tmp_path):
        db_file = str(tmp_path / "queue.db")
        q1 = MemoryQueue(sqlite_path=db_file)
        await q1.enqueue(Job(handler="persisted", priority=2))
        await q1.close()

        q2 = MemoryQueue(sqlite_path=db_file)
        assert await q2.size() == 1
        restored = await q2.dequeue()
        assert restored is not None
        assert restored.handler == "persisted"
        assert restored.priority == 2
        await q2.close()

    @pytest.mark.anyio
    async def test_completed_job_not_restored(self, tmp_path):
        db_file = str(tmp_path / "queue2.db")
        q1 = MemoryQueue(sqlite_path=db_file)
        job = Job(handler="done")
        await q1.enqueue(job)
        await q1.dequeue()
        job.status = JobStatus.COMPLETED
        await q1.update_job(job)
        await q1.close()

        q2 = MemoryQueue(sqlite_path=db_file)
        assert await q2.size() == 0
        await q2.close()

    @pytest.mark.anyio
    async def test_remove_job_deletes_from_store(self, tmp_path):
        db_file = str(tmp_path / "queue3.db")
        q1 = MemoryQueue(sqlite_path=db_file)
        job = Job(handler="doomed")
        await q1.enqueue(job)
        await q1.remove_job(job.id)
        await q1.close()

        q2 = MemoryQueue(sqlite_path=db_file)
        assert await q2.size() == 0
        await q2.close()
