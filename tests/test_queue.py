"""Tests for fenrir.queue — Lightweight job queue system."""
import asyncio

import pytest

from fenrir.queue import Job, JobStatus, MemoryQueue, Queue, Worker

# ═══════════════════════════════════════════════════════════════════════
# Job Tests
# ═══════════════════════════════════════════════════════════════════════

class TestJob:
    def test_job_creation(self):
        job = Job(handler="test_handler", args=(1, 2), kwargs={"key": "value"})
        assert job.handler == "test_handler"
        assert job.args == (1, 2)
        assert job.kwargs == {"key": "value"}
        assert job.status == JobStatus.PENDING

    def test_job_to_dict(self):
        job = Job(id="test-id", handler="test_handler")
        data = job.to_dict()
        assert data["id"] == "test-id"
        assert data["handler"] == "test_handler"
        assert data["status"] == "pending"

    def test_job_from_dict(self):
        data = {
            "id": "test-id",
            "handler": "test_handler",
            "status": "pending",
        }
        job = Job.from_dict(data)
        assert job.id == "test-id"
        assert job.handler == "test_handler"
        assert job.status == JobStatus.PENDING


# ═══════════════════════════════════════════════════════════════════════
# MemoryQueue Tests
# ═══════════════════════════════════════════════════════════════════════

class TestMemoryQueue:
    @pytest.mark.anyio
    async def test_enqueue_dequeue(self):
        queue = MemoryQueue()
        job = Job(handler="test_handler")
        await queue.enqueue(job)
        dequeued = await queue.dequeue()
        assert dequeued is not None
        assert dequeued.id == job.id

    @pytest.mark.anyio
    async def test_size(self):
        queue = MemoryQueue()
        await queue.enqueue(Job(handler="h1"))
        await queue.enqueue(Job(handler="h2"))
        size = await queue.size()
        assert size == 2

    @pytest.mark.anyio
    async def test_get_job(self):
        queue = MemoryQueue()
        job = Job(id="test-id", handler="test_handler")
        await queue.enqueue(job)
        fetched = await queue.get_job("test-id")
        assert fetched is not None
        assert fetched.id == "test-id"

    @pytest.mark.anyio
    async def test_update_job(self):
        queue = MemoryQueue()
        job = Job(id="test-id", handler="test_handler")
        await queue.enqueue(job)
        job.status = JobStatus.COMPLETED
        await queue.update_job(job)
        updated = await queue.get_job("test-id")
        assert updated.status == JobStatus.COMPLETED

    @pytest.mark.anyio
    async def test_remove_job(self):
        queue = MemoryQueue()
        job = Job(id="test-id", handler="test_handler")
        await queue.enqueue(job)
        result = await queue.remove_job("test-id")
        assert result is True
        assert await queue.get_job("test-id") is None

    @pytest.mark.anyio
    async def test_priority_order(self):
        queue = MemoryQueue()
        job_low = Job(handler="low", priority=0)
        job_high = Job(handler="high", priority=10)
        await queue.enqueue(job_low)
        await queue.enqueue(job_high)
        first = await queue.dequeue()
        assert first.handler == "high"


# ═══════════════════════════════════════════════════════════════════════
# Queue Wrapper Tests
# ═══════════════════════════════════════════════════════════════════════

class TestQueueWrapper:
    @pytest.mark.anyio
    async def test_handler_registration(self):
        queue = Queue()

        @queue.handler("test_job")
        async def test_handler(x):
            return x * 2

        assert "test_job" in queue._handlers

    @pytest.mark.anyio
    async def test_enqueue(self):
        queue = Queue()

        @queue.handler("test_job")
        async def test_handler(x):
            return x * 2

        job = await queue.enqueue("test_job", 5)
        assert job is not None
        assert job.handler == "test_job"

    @pytest.mark.anyio
    async def test_process_next(self):
        queue = Queue()
        results = []

        @queue.handler("test_job")
        async def test_handler(x):
            results.append(x * 2)
            return x * 2

        await queue.enqueue("test_job", 5)
        job = await queue.process_next()
        assert job.status == JobStatus.COMPLETED
        assert results == [10]

    @pytest.mark.anyio
    async def test_process_sync_handler(self):
        queue = Queue()
        results = []

        @queue.handler("sync_job")
        def sync_handler(x):
            results.append(x * 2)
            return x * 2

        await queue.enqueue("sync_job", 5)
        job = await queue.process_next()
        assert job.status == JobStatus.COMPLETED
        assert results == [10]

    @pytest.mark.anyio
    async def test_process_unknown_handler(self):
        queue = Queue()
        await queue.enqueue("unknown_handler")
        job = await queue.process_next()
        assert job.status == JobStatus.FAILED
        assert "Handler not found" in job.error

    @pytest.mark.anyio
    async def test_retry_on_failure(self):
        queue = Queue(retry_backoff=0.05)
        attempt_count = 0

        @queue.handler("failing_job")
        async def failing_handler():
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 3:
                raise ValueError("Not yet")
            return "success"

        await queue.enqueue("failing_job", max_retries=3)
        # Retries are scheduled with backoff, so poll until completion.
        for _ in range(100):
            job = await queue.process_next()
            if job and job.status == JobStatus.COMPLETED:
                break
            await asyncio.sleep(0.05)
        assert job is not None
        assert job.status == JobStatus.COMPLETED
        assert attempt_count == 3

    @pytest.mark.anyio
    async def test_cancel_job(self):
        queue = Queue()

        @queue.handler("test_job")
        async def test_handler():
            return "done"

        job = await queue.enqueue("test_job")
        result = await queue.cancel(job.id)
        assert result is True

    @pytest.mark.anyio
    async def test_job_timeout(self):
        queue = Queue()

        @queue.handler("slow_job")
        async def slow_handler():
            await asyncio.sleep(10)
            return "done"

        job = await queue.enqueue("slow_job", timeout=0.1)
        job = await queue.process_next()
        assert job.status == JobStatus.FAILED
        assert "timed out" in job.error

    @pytest.mark.anyio
    async def test_queue_size(self):
        queue = Queue()

        @queue.handler("test_job")
        async def test_handler():
            pass

        await queue.enqueue("test_job")
        await queue.enqueue("test_job")
        size = await queue.size()
        assert size == 2


# ═══════════════════════════════════════════════════════════════════════
# Worker Tests
# ═══════════════════════════════════════════════════════════════════════

class TestWorker:
    @pytest.mark.anyio
    async def test_worker_start_stop(self):
        queue = Queue()
        worker = Worker(queue, concurrency=1)
        await worker.start()
        assert worker._running is True
        await worker.stop()
        assert worker._running is False

    @pytest.mark.anyio
    async def test_worker_processes_jobs(self):
        queue = Queue()
        results = []

        @queue.handler("test_job")
        async def test_handler(x):
            results.append(x)
            return x

        await queue.enqueue("test_job", 1)
        await queue.enqueue("test_job", 2)
        worker = Worker(queue, concurrency=1, max_jobs=2)
        await worker.run()
        assert results == [1, 2]
