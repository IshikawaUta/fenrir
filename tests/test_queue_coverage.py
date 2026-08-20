"""Targeted coverage tests for fenrir.queue internals."""
import asyncio
import time

import pytest

from fenrir.compat import to_thread  # noqa: F401
from fenrir.json import json_dumps
from fenrir.queue import Job, JobStatus, MemoryQueue, Queue, RedisQueue, Worker


@pytest.fixture
def redis_client():
    import fakeredis.aioredis

    return fakeredis.aioredis.FakeRedis(decode_responses=True)

# ═══════════════════════════════════════════════════════════════════════
# MemoryQueue internals
# ═══════════════════════════════════════════════════════════════════════


class TestMemoryQueueCoverage:
    @pytest.mark.anyio
    async def test_delayed_enqueue_and_promote(self, monkeypatch):
        queue = MemoryQueue()
        job = Job(handler="h", delay=0.2)
        await queue.enqueue(job)
        assert job.id in queue._delayed
        await asyncio.sleep(0.3)
        queue._promote_ready()
        assert job.id not in queue._delayed
        assert not queue._queue.empty()

    @pytest.mark.anyio
    async def test_promote_ready_missing_job(self):
        queue = MemoryQueue()
        queue._delayed["ghost"] = time.time() - 10
        assert queue._promote_ready() is True
        assert "ghost" not in queue._delayed

    @pytest.mark.anyio
    async def test_promote_ready_none(self):
        queue = MemoryQueue()
        assert queue._promote_ready() is False

    @pytest.mark.anyio
    async def test_dequeue_skips_non_pending(self):
        queue = MemoryQueue()
        job = Job(handler="h")
        await queue.enqueue(job)
        job.status = JobStatus.COMPLETED
        await queue.update_job(job)
        assert await queue.dequeue() is None

    @pytest.mark.anyio
    async def test_dequeue_after_running(self):
        queue = MemoryQueue()
        job = Job(handler="h")
        await queue.enqueue(job)
        await queue.dequeue()
        assert await queue.dequeue() is None

    @pytest.mark.anyio
    async def test_peek(self):
        queue = MemoryQueue()
        await queue.enqueue(Job(handler="a", priority=1))
        await queue.enqueue(Job(handler="b", priority=5))
        jobs = await queue.peek(n=1)
        assert len(jobs) == 1
        jobs2 = await queue.peek(n=10)
        assert [j.handler for j in jobs2] == ["b", "a"]

    @pytest.mark.anyio
    async def test_peek_skips_completed(self):
        queue = MemoryQueue()
        done = Job(handler="done")
        await queue.enqueue(done)
        done.status = JobStatus.COMPLETED
        await queue.update_job(done)
        await queue.enqueue(Job(handler="pending"))
        jobs = await queue.peek(n=10)
        assert [j.handler for j in jobs] == ["pending"]

    @pytest.mark.anyio
    async def test_requeue(self):
        queue = MemoryQueue()
        job = Job(handler="h")
        await queue.enqueue(job)
        await queue.dequeue()
        job.status = JobStatus.RETRY
        await queue.requeue(job)
        assert job.status == JobStatus.PENDING
        assert await queue.size() == 1

    @pytest.mark.anyio
    async def test_requeue_delayed(self):
        queue = MemoryQueue()
        job = Job(handler="h")
        await queue.enqueue(job)
        job.delay = 0.1
        await queue.requeue(job)
        assert job.id in queue._delayed

    @pytest.mark.anyio
    async def test_get_jobs_by_status(self):
        queue = MemoryQueue()
        await queue.enqueue(Job(handler="h"))
        jobs = await queue.get_jobs_by_status(JobStatus.PENDING)
        assert len(jobs) == 1
        assert await queue.get_jobs_by_status(JobStatus.COMPLETED) == []

    @pytest.mark.anyio
    async def test_remove_job_missing(self):
        queue = MemoryQueue()
        assert await queue.remove_job("missing") is False

    @pytest.mark.anyio
    async def test_backend_property(self):
        queue = Queue()
        assert isinstance(queue.backend, MemoryQueue)

    @pytest.mark.anyio
    async def test_register(self):
        queue = Queue()
        queue.register("direct", lambda: 1)
        assert "direct" in queue._handlers

    @pytest.mark.anyio
    async def test_handler_name_default(self):
        queue = Queue()

        @queue.handler()
        def auto_named():
            pass

        assert "auto_named" in queue._handlers or any(
            k.endswith("auto_named") for k in queue._handlers
        )

    @pytest.mark.anyio
    async def test_get_job(self):
        queue = Queue()
        job = await queue.enqueue("h")
        assert (await queue.get_job(job.id)) is not None

    @pytest.mark.anyio
    async def test_cancel_not_found(self):
        queue = Queue()
        assert await queue.cancel("missing") is False

    @pytest.mark.anyio
    async def test_cancel_failed_job(self):
        queue = Queue()
        job = await queue.enqueue("h")
        job.status = JobStatus.FAILED
        await queue._backend.update_job(job)
        assert await queue.cancel(job.id) is False


# ═══════════════════════════════════════════════════════════════════════
# SQLite persistence
# ═══════════════════════════════════════════════════════════════════════


class TestSqlitePersistence:
    @pytest.mark.anyio
    async def test_persist_and_restore(self, tmp_path):
        db_path = str(tmp_path / "queue.db")
        q1 = MemoryQueue(sqlite_path=db_path)
        job = Job(handler="h", args=(1,))
        await q1.enqueue(job)
        await q1.close()
        assert q1._db is None

        q2 = MemoryQueue(sqlite_path=db_path)
        restored = await q2.get_job(job.id)
        assert restored is not None
        assert restored.handler == "h"
        await q2.close()

    @pytest.mark.anyio
    async def test_restore_delayed_ready(self, tmp_path):
        db_path = str(tmp_path / "q2.db")
        q1 = MemoryQueue(sqlite_path=db_path)
        job = Job(handler="h", delay=0.01)
        await q1.enqueue(job)
        await q1.close()

        await asyncio.sleep(0.05)
        q2 = MemoryQueue(sqlite_path=db_path)
        await q2._ensure_db()
        assert not q2._queue.empty()
        await q2.close()

    @pytest.mark.anyio
    async def test_restore_delayed_not_ready(self, tmp_path):
        db_path = str(tmp_path / "q3.db")
        q1 = MemoryQueue(sqlite_path=db_path)
        job = Job(handler="h", delay=100)
        await q1.enqueue(job)
        await q1.close()

        q2 = MemoryQueue(sqlite_path=db_path)
        await q2._ensure_db()
        assert job.id in q2._delayed
        assert q2._queue is None or q2._queue.empty()
        await q2.close()

    @pytest.mark.anyio
    async def test_restore_skips_bad_data(self, tmp_path):
        import aiosqlite

        db_path = str(tmp_path / "q4.db")
        db = await aiosqlite.connect(db_path)
        await db.execute(
            "CREATE TABLE IF NOT EXISTS queue_jobs "
            "(id TEXT PRIMARY KEY, data TEXT NOT NULL, status TEXT NOT NULL)"
        )
        await db.execute("INSERT INTO queue_jobs VALUES (?, ?, ?)", ("bad", "not-json", "pending"))
        done_job = Job(handler="done")
        done_job.status = JobStatus.COMPLETED
        await db.execute(
            "INSERT INTO queue_jobs VALUES (?, ?, ?)",
            ("done", json_dumps(done_job.to_dict()), "completed"),
        )
        await db.commit()
        await db.close()

        q = MemoryQueue(sqlite_path=db_path)
        await q._ensure_db()
        assert await q.get_job("bad") is None
        assert await q.get_job("done") is None
        await q.close()

    @pytest.mark.anyio
    async def test_restore_direct_no_db(self):
        q = MemoryQueue()
        await q._restore_from_db()

    @pytest.mark.anyio
    async def test_close_no_db(self):
        q = MemoryQueue()
        await q.close()
        await q._run_cleanup()

    @pytest.mark.anyio
    async def test_reopen_same_instance(self, tmp_path):
        db_path = str(tmp_path / "q7.db")
        q = MemoryQueue(sqlite_path=db_path)
        await q.enqueue(Job(handler="h"))
        await q.close()
        await q.enqueue(Job(handler="h2"))
        assert await q.size() == 2
        await q.close()

    @pytest.mark.anyio
    async def test_persist_delete_after_remove(self, tmp_path):
        db_path = str(tmp_path / "q5.db")
        q1 = MemoryQueue(sqlite_path=db_path)
        job = Job(handler="h")
        await q1.enqueue(job)
        await q1.close()

        q2 = MemoryQueue(sqlite_path=db_path)
        await q2._ensure_db()
        await q2.remove_job(job.id)
        await q2.close()

        q3 = MemoryQueue(sqlite_path=db_path)
        assert await q3.get_job(job.id) is None
        await q3.close()

    @pytest.mark.anyio
    async def test_run_cleanup(self, tmp_path):
        queue = MemoryQueue(sqlite_path=str(tmp_path / "q6.db"))
        job = Job(handler="h")
        await queue.enqueue(job)
        job.status = JobStatus.COMPLETED
        await queue.update_job(job)
        assert len(queue._cleanup_entries) == 1
        assert queue._cleanup_task is not None
        await queue._cleanup_task
        assert job.id not in queue._jobs
        await queue.close()


# ═══════════════════════════════════════════════════════════════════════
# RedisQueue
# ═══════════════════════════════════════════════════════════════════════


class TestRedisQueueCoverage:
    def make_redis_queue(self, redis_client):
        q = RedisQueue(prefix="fenrir:test:")
        q._redis = redis_client
        return q

    @pytest.mark.anyio
    async def test_lazy_connect_error(self, monkeypatch):
        import builtins

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "redis" or name.startswith("redis."):
                raise ImportError("no redis")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        q = RedisQueue()
        with pytest.raises(ImportError):
            await q._get_redis()

    @pytest.mark.anyio
    async def test_enqueue_promote_dequeue(self, redis_client):
        queue = self.make_redis_queue(redis_client)
        job = Job(handler="h", args=(1,))
        await queue.enqueue(job)
        assert await queue.size() == 1
        out = await queue.dequeue()
        assert out is not None
        assert out.id == job.id
        assert out.status == JobStatus.RUNNING

    @pytest.mark.anyio
    async def test_delayed_enqueue(self, redis_client):
        queue = self.make_redis_queue(redis_client)
        job = Job(handler="h", delay=0.05)
        await queue.enqueue(job)
        assert await queue.size() == 0
        assert len(await queue._redis.zrangebyscore(queue._key("delayed"), 0, time.time() + 1)) == 1

    @pytest.mark.anyio
    async def test_promote_delayed_empty(self, redis_client):
        queue = self.make_redis_queue(redis_client)
        await queue._promote_delayed()

    @pytest.mark.anyio
    async def test_dequeue_empty(self, redis_client):
        queue = self.make_redis_queue(redis_client)
        assert await queue.dequeue() is None

    @pytest.mark.anyio
    async def test_dequeue_missing_data(self, redis_client):
        queue = self.make_redis_queue(redis_client)
        await queue._redis.zadd(queue._key("pending"), {"orphan": 0})
        assert await queue.dequeue() is None
        assert await queue._redis.zcard(queue._key("pending")) == 0

    @pytest.mark.anyio
    async def test_requeue(self, redis_client):
        queue = self.make_redis_queue(redis_client)
        job = Job(handler="h")
        await queue.requeue(job)
        assert await queue.size() == 1

    @pytest.mark.anyio
    async def test_requeue_delayed(self, redis_client):
        queue = self.make_redis_queue(redis_client)
        job = Job(handler="h", delay=0.1)
        await queue.requeue(job)
        assert await queue.size() == 0

    @pytest.mark.anyio
    async def test_get_update_remove(self, redis_client):
        queue = self.make_redis_queue(redis_client)
        job = Job(handler="h")
        await queue.enqueue(job)
        fetched = await queue.get_job(job.id)
        assert fetched is not None
        job.status = JobStatus.COMPLETED
        await queue.update_job(job)
        fetched2 = await queue.get_job(job.id)
        assert fetched2.status == JobStatus.COMPLETED
        assert await queue.remove_job(job.id) is True
        assert await queue.remove_job(job.id) is False
        assert await queue.get_job(job.id) is None

    @pytest.mark.anyio
    async def test_get_jobs_by_status(self, redis_client):
        queue = self.make_redis_queue(redis_client)
        await queue.enqueue(Job(handler="h"))
        jobs = await queue.get_jobs_by_status(JobStatus.PENDING)
        assert len(jobs) == 1

    @pytest.mark.anyio
    async def test_get_redis_reconnect(self, redis_client, monkeypatch):
        import redis.asyncio

        q = RedisQueue()
        monkeypatch.setattr(redis.asyncio, "from_url", lambda *a, **k: redis_client)
        r1 = await q._get_redis()
        assert r1 is redis_client
        await q.close()
        r2 = await q._get_redis()
        assert r2 is redis_client

    @pytest.mark.anyio
    async def test_promote_delayed_ready(self, redis_client):
        queue = self.make_redis_queue(redis_client)
        job = Job(handler="h")
        await queue._redis.hset(queue._key("jobs"), job.id, json_dumps(job.to_dict()))
        await queue._redis.zadd(queue._key("delayed"), {job.id: time.time() - 1})
        await queue._promote_delayed()
        assert await queue.size() == 1

    @pytest.mark.anyio
    async def test_promote_delayed_missing_data(self, redis_client):
        queue = self.make_redis_queue(redis_client)
        await queue._redis.zadd(queue._key("delayed"), {"orphan": time.time() - 1})
        await queue._promote_delayed()
        assert await queue.size() == 0

    @pytest.mark.anyio
    async def test_get_jobs_by_status_skip(self, redis_client):
        queue = self.make_redis_queue(redis_client)
        job = Job(handler="h")
        await queue.enqueue(job)
        jobs = await queue.get_jobs_by_status(JobStatus.COMPLETED)
        assert jobs == []

    @pytest.mark.anyio
    async def test_close_and_context(self, redis_client):
        queue = self.make_redis_queue(redis_client)
        await queue.close()
        assert queue._redis is None
        queue._redis = redis_client
        async with queue as q:
            assert q is queue
        assert queue._redis is None

    @pytest.mark.anyio
    async def test_close_with_none(self):
        queue = RedisQueue()
        await queue.close()


# ═══════════════════════════════════════════════════════════════════════
# Queue process_next paths
# ═══════════════════════════════════════════════════════════════════════


class TestProcessNextPaths:
    @pytest.mark.anyio
    async def test_sync_handler_with_timeout(self):
        queue = Queue()

        def sync(x):
            return x + 1

        queue.register("sync", sync)
        await queue.enqueue("sync", 1, timeout=5)
        job = await queue.process_next()
        assert job.status == JobStatus.COMPLETED
        assert job.result == 2

    @pytest.mark.anyio
    async def test_exhaust_retries_dead_letter(self):
        dead = []
        queue = Queue(retry_backoff=0.01, dead_letter_handler=lambda j: dead.append(j))

        async def fail():
            raise RuntimeError("always")

        queue.register("fail", fail)
        await queue.enqueue("fail", max_retries=0)
        job = await queue.process_next()
        assert job.status == JobStatus.FAILED
        assert job.error == "always"
        assert dead == [job]

    @pytest.mark.anyio
    async def test_dead_letter_async_and_error(self):
        calls = []

        async def async_dl(job):
            calls.append(job)

        def bad_dl(job):
            raise RuntimeError("dl boom")

        queue = Queue(dead_letter_handler=async_dl)
        queue.register("f", _fail_handler)
        await queue.enqueue("f", max_retries=0)
        await queue.process_next()
        assert len(calls) == 1

        queue2 = Queue(dead_letter_handler=bad_dl)
        queue2.register("f", _fail_handler)
        await queue2.enqueue("f", max_retries=0)
        job = await queue2.process_next()
        assert job.status == JobStatus.FAILED

    @pytest.mark.anyio
    async def test_dead_letter_none(self):
        queue = Queue()
        queue.register("f", _fail_handler)
        await queue.enqueue("f", max_retries=0)
        job = await queue.process_next()
        assert job.status == JobStatus.FAILED

    @pytest.mark.anyio
    async def test_worker_cancelled_loop(self):
        queue = Queue()

        @queue.handler("h")
        async def h():
            return 1

        worker = Worker(queue, concurrency=1, poll_interval=0.01)
        task = asyncio.create_task(worker.run())
        await asyncio.sleep(0.05)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        assert worker._running is False

    @pytest.mark.anyio
    async def test_cancel_without_remove(self):
        class NoRemoveBackend:
            def __init__(self):
                self.jobs = {}

            async def enqueue(self, job):
                self.jobs[job.id] = job

            async def get_job(self, job_id):
                return self.jobs.get(job_id)

            async def update_job(self, job):
                self.jobs[job.id] = job

        queue = Queue(backend=NoRemoveBackend())
        job = await queue.enqueue("h")
        assert await queue.cancel(job.id) is True

    @pytest.mark.anyio
    async def test_worker_stop_via_flag(self):
        queue = Queue()

        @queue.handler("h")
        async def h():
            return 1

        worker = Worker(queue, concurrency=1, poll_interval=0.01)
        task = asyncio.create_task(worker.run())
        await asyncio.sleep(0.05)
        worker._running = False
        await task
        assert worker._running is False

    @pytest.mark.anyio
    async def test_worker_loop_no_jobs(self):
        queue = Queue()
        worker = Worker(queue, concurrency=1, poll_interval=0.01, max_jobs=1)
        await worker.start()
        await asyncio.sleep(0.05)
        await worker.stop()

    @pytest.mark.anyio
    async def test_worker_loop_stopped(self):
        queue = Queue()
        worker = Worker(queue, concurrency=1)
        worker._running = False
        await worker._worker_loop(0)

    @pytest.mark.anyio
    async def test_worker_loop_backend_error(self):
        class BrokenBackend:
            async def dequeue(self):
                raise RuntimeError("backend down")

        queue = Queue(backend=BrokenBackend())
        worker = Worker(queue, concurrency=1, poll_interval=0.01, max_jobs=0)
        worker._running = True
        task = asyncio.create_task(worker._worker_loop(0))
        await asyncio.sleep(0.05)
        worker._running = False
        await task

    @pytest.mark.anyio
    async def test_worker_loop_exception(self):
        queue = Queue()
        queue.register("boom", _fail_handler)
        await queue.enqueue("boom", max_retries=0)
        worker = Worker(queue, concurrency=1, poll_interval=0.01, max_jobs=1)
        await worker.run()
        assert worker._jobs_processed == 1


async def _fail_handler():
    raise RuntimeError("always")
