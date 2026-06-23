"""Tests for fenrir.queue — RedisQueue with fakeredis."""
import asyncio
import json
import pytest
from unittest.mock import patch, MagicMock
from fenrir.queue import Job, JobStatus, RedisQueue, Queue


def _make_job(handler="test", priority=0, **kw):
    return Job(handler=handler, priority=priority, **kw)


# ═══════════════════════════════════════════════════════════════════════
# RedisQueue Tests (fakeredis)
# ═══════════════════════════════════════════════════════════════════════

@pytest.fixture
def fake_redis():
    """Create a fakeredis instance."""
    import fakeredis.aioredis
    server = fakeredis.FakeServer()
    return fakeredis.aioredis.FakeRedis(server=server)


@pytest.fixture
def redis_queue(fake_redis):
    """Create a RedisQueue with fakeredis backend."""
    rq = RedisQueue(prefix="test:queue:")
    rq._redis = fake_redis
    return rq


class TestRedisQueue:
    @pytest.mark.anyio
    async def test_enqueue_dequeue(self, redis_queue):
        job = _make_job()
        await redis_queue.enqueue(job)
        result = await redis_queue.dequeue()
        assert result is not None
        assert result.id == job.id
        assert result.status == JobStatus.RUNNING

    @pytest.mark.anyio
    async def test_dequeue_empty(self, redis_queue):
        result = await redis_queue.dequeue()
        assert result is None

    @pytest.mark.anyio
    async def test_size(self, redis_queue):
        await redis_queue.enqueue(_make_job())
        assert await redis_queue.size() == 1
        await redis_queue.enqueue(_make_job())
        assert await redis_queue.size() == 2

    @pytest.mark.anyio
    async def test_requeue(self, redis_queue):
        job = _make_job()
        await redis_queue.enqueue(job)
        await redis_queue.dequeue()
        await redis_queue.requeue(job)
        assert await redis_queue.size() == 1

    @pytest.mark.anyio
    async def test_get_job(self, redis_queue):
        job = _make_job()
        await redis_queue.enqueue(job)
        found = await redis_queue.get_job(job.id)
        assert found is not None
        assert found.id == job.id

    @pytest.mark.anyio
    async def test_get_job_not_found(self, redis_queue):
        result = await redis_queue.get_job("nonexistent")
        assert result is None

    @pytest.mark.anyio
    async def test_update_job(self, redis_queue):
        job = _make_job()
        await redis_queue.enqueue(job)
        job.status = JobStatus.COMPLETED
        await redis_queue.update_job(job)
        found = await redis_queue.get_job(job.id)
        assert found.status == JobStatus.COMPLETED

    @pytest.mark.anyio
    async def test_remove_job(self, redis_queue):
        job = _make_job()
        await redis_queue.enqueue(job)
        assert await redis_queue.remove_job(job.id) is True
        assert await redis_queue.get_job(job.id) is None

    @pytest.mark.anyio
    async def test_remove_job_not_found(self, redis_queue):
        assert await redis_queue.remove_job("nonexistent") is False

    @pytest.mark.anyio
    async def test_get_jobs_by_status(self, redis_queue):
        await redis_queue.enqueue(_make_job())
        await redis_queue.enqueue(_make_job())
        jobs = await redis_queue.get_jobs_by_status(JobStatus.PENDING)
        assert len(jobs) == 2

    @pytest.mark.anyio
    async def test_enqueue_delayed(self, redis_queue):
        job = _make_job(delay=60)
        await redis_queue.enqueue(job)
        # Delayed job goes to delayed sorted set, not pending
        assert await redis_queue.size() == 0

    @pytest.mark.anyio
    async def test_context_manager(self, redis_queue):
        async with redis_queue:
            assert redis_queue._redis is not None
        # After context exit, connection should be closed

    @pytest.mark.anyio
    async def test_key_method(self, redis_queue):
        assert redis_queue._key("jobs") == "test:queue:jobs"


# ═══════════════════════════════════════════════════════════════════════
# RedisQueue with Queue wrapper
# ═══════════════════════════════════════════════════════════════════════

class TestRedisQueueWithQueue:
    @pytest.mark.anyio
    async def test_enqueue_process(self, fake_redis):
        rq = RedisQueue(prefix="test:")
        rq._redis = fake_redis
        q = Queue(backend=rq)

        @q.handler("work")
        async def work(x):
            return x * 2

        await q.enqueue("work", 5)
        job = await q.process_next()
        assert job.status == JobStatus.COMPLETED
        assert job.result == 10

    @pytest.mark.anyio
    async def test_handler_not_found(self, fake_redis):
        rq = RedisQueue(prefix="test:")
        rq._redis = fake_redis
        q = Queue(backend=rq)
        await q.enqueue("missing")
        job = await q.process_next()
        assert job.status == JobStatus.FAILED

    @pytest.mark.anyio
    async def test_worker_processes(self, fake_redis):
        rq = RedisQueue(prefix="test:")
        rq._redis = fake_redis
        q = Queue(backend=rq)
        count = 0

        @q.handler("inc")
        async def inc():
            nonlocal count
            count += 1

        for _ in range(3):
            await q.enqueue("inc")

        from fenrir.queue import Worker
        w = Worker(q, concurrency=1, poll_interval=0.01, max_jobs=3)
        await w.run()
        assert count == 3
