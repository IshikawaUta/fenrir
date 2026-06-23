"""
fenrir.queue — Lightweight job queue system for Fenrir.

Provides async job processing with pluggable backends:
- MemoryQueue: In-process async queue (for development/small apps)
- RedisQueue: Redis-backed distributed queue (for production)

Features:
- Delayed jobs
- Retry with backoff
- Job priorities
- Job status tracking
- Worker pools

Usage::

    from fenrir.queue import Queue, Job, Worker

    # Configure queue
    queue = Queue(backend=MemoryQueue())

    # Define a job handler
    @queue.handler("send_email")
    async def send_email(to: str, subject: str, body: str):
        await smtp_send(to, subject, body)

    # Enqueue jobs
    await queue.enqueue("send_email", to="user@example.com", subject="Hello", body="Hi!")

    # Delayed job
    await queue.enqueue("send_email", delay=300, to="user@example.com", ...)

    # Start worker
    worker = Worker(queue, concurrency=4)
    await worker.start()
"""
from __future__ import annotations

import asyncio
import enum
import importlib
import inspect
import logging
import time
import traceback
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Type, Union

from fenrir.compat import to_thread
from fenrir.json import json_dumps, json_loads

logger = logging.getLogger("fenrir.queue")


class JobStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRY = "retry"
    CANCELLED = "cancelled"


@dataclass
class Job:
    """Represents a queued job."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    handler: str = ""
    args: tuple = ()
    kwargs: dict = field(default_factory=dict)
    status: JobStatus = JobStatus.PENDING
    priority: int = 0
    max_retries: int = 3
    retry_count: int = 0
    delay: float = 0
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    result: Any = None
    error: Optional[str] = None
    timeout: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "handler": self.handler,
            "args": list(self.args),  # Convert tuple to list for JSON
            "kwargs": self.kwargs,
            "status": self.status.value,
            "priority": self.priority,
            "max_retries": self.max_retries,
            "retry_count": self.retry_count,
            "delay": self.delay,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "result": str(self.result) if self.result is not None else None,
            "error": self.error,
            "timeout": self.timeout,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Job":
        data = dict(data)  # Don't mutate input
        data["status"] = JobStatus(data.get("status", "pending"))
        # Convert args back to tuple
        if "args" in data and isinstance(data["args"], list):
            data["args"] = tuple(data["args"])
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class QueueBackend:
    """Base queue backend interface."""

    async def enqueue(self, job: Job) -> None:
        raise NotImplementedError

    async def dequeue(self) -> Optional[Job]:
        raise NotImplementedError

    async def peek(self, n: int = 1) -> List[Job]:
        raise NotImplementedError

    async def size(self) -> int:
        raise NotImplementedError

    async def requeue(self, job: Job) -> None:
        raise NotImplementedError

    async def get_job(self, job_id: str) -> Optional[Job]:
        raise NotImplementedError

    async def update_job(self, job: Job) -> None:
        raise NotImplementedError

    async def remove_job(self, job_id: str) -> bool:
        raise NotImplementedError

    async def get_jobs_by_status(self, status: JobStatus) -> List[Job]:
        raise NotImplementedError


class MemoryQueue(QueueBackend):
    """In-process async queue using asyncio.PriorityQueue.

    Best for single-process applications and development.
    """

    def __init__(self, max_size: int = 10000) -> None:
        self._queue: Optional[asyncio.PriorityQueue] = None
        self._jobs: Dict[str, Job] = {}
        self._processing: Set[str] = set()
        self._max_size = max_size
        self._cleanup_entries: List[tuple] = []  # (timestamp, job_id)
        self._cleanup_task: Optional[asyncio.Task] = None

    def _get_queue(self) -> asyncio.PriorityQueue:
        if self._queue is None:
            self._queue = asyncio.PriorityQueue()
        return self._queue

    async def enqueue(self, job: Job) -> None:
        self._jobs[job.id] = job
        await self._get_queue().put((-job.priority, job.created_at, job.id))
        logger.debug("Enqueued job %s (handler=%s)", job.id, job.handler)

    async def dequeue(self) -> Optional[Job]:
        q = self._get_queue()
        while not q.empty():
            try:
                _, _, job_id = q.get_nowait()
                job = self._jobs.get(job_id)
                if job and job.status in (JobStatus.PENDING, JobStatus.RETRY):
                    self._processing.add(job_id)
                    return job
                # Job was cancelled or already running — skip
            except asyncio.QueueEmpty:
                break
        return None

    async def peek(self, n: int = 1) -> List[Job]:
        jobs = []
        for job in self._jobs.values():
            if job.status in (JobStatus.PENDING, JobStatus.RETRY):
                jobs.append(job)
                if len(jobs) >= n:
                    break
        return sorted(jobs, key=lambda j: (-j.priority, j.created_at))

    async def size(self) -> int:
        return sum(
            1 for j in self._jobs.values()
            if j.status in (JobStatus.PENDING, JobStatus.RETRY)
        )

    async def requeue(self, job: Job) -> None:
        job.status = JobStatus.PENDING
        await self._get_queue().put((-job.priority, job.created_at, job.id))

    async def get_job(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)

    async def update_job(self, job: Job) -> None:
        self._jobs[job.id] = job
        # Clean up completed/failed/cancelled jobs to prevent memory leak
        if job.status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
            self._processing.discard(job.id)
            # Mark for cleanup after 60 seconds
            import time as _time
            self._cleanup_entries.append((_time.time() + 60, job.id))
            # Start single cleanup task if not running
            if self._cleanup_task is None or self._cleanup_task.done():
                self._cleanup_task = asyncio.create_task(self._run_cleanup())

    async def _run_cleanup(self) -> None:
        """Single background task that processes all cleanup entries."""
        import time as _time
        while self._cleanup_entries:
            now = _time.time()
            # Find entries ready for cleanup
            ready = [i for i, (ts, _) in enumerate(self._cleanup_entries) if ts <= now]
            for i in reversed(ready):
                _, job_id = self._cleanup_entries.pop(i)
                self._jobs.pop(job_id, None)
            if self._cleanup_entries:
                # Sleep until next entry is ready
                earliest = min(ts for ts, _ in self._cleanup_entries)
                await asyncio.sleep(max(0, earliest - _time.time()))
            else:
                break

    async def remove_job(self, job_id: str) -> bool:
        if job_id in self._jobs:
            del self._jobs[job_id]
            self._processing.discard(job_id)
            return True
        return False

    async def get_jobs_by_status(self, status: JobStatus) -> List[Job]:
        return [j for j in self._jobs.values() if j.status == status]


class RedisQueue(QueueBackend):
    """Redis-backed distributed queue.

    Requires the ``redis`` package.
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/0",
        prefix: str = "fenrir:queue:",
    ) -> None:
        self._redis_url = redis_url
        self._prefix = prefix
        self._redis = None
        self._init_lock = asyncio.Lock()

    async def _get_redis(self):
        if self._redis is None:
            async with self._init_lock:
                if self._redis is None:
                    try:
                        import redis.asyncio as aioredis
                        self._redis = aioredis.from_url(self._redis_url, decode_responses=True)
                    except ImportError:
                        raise ImportError("redis is required for RedisQueue")
        return self._redis

    def _key(self, name: str) -> str:
        return f"{self._prefix}{name}"

    async def enqueue(self, job: Job) -> None:
        redis = await self._get_redis()
        data = json_dumps(job.to_dict())
        await redis.hset(self._key("jobs"), job.id, data)
        if job.delay > 0:
            # Store delayed job with a score of current time + delay
            schedule_time = job.created_at + job.delay
            await redis.zadd(self._key("delayed"), {job.id: schedule_time})
        else:
            await redis.zadd(self._key("pending"), {job.id: -job.priority})
        logger.debug("Enqueued job %s", job.id)

    async def dequeue(self) -> Optional[Job]:
        redis = await self._get_redis()
        result = await redis.zpopmin(self._key("pending"), count=1)
        if not result:
            return None
        job_id = result[0][0]
        data = await redis.hget(self._key("jobs"), job_id)
        if data:
            job = Job.from_dict(json_loads(data))
            job.status = JobStatus.RUNNING
            job.started_at = time.time()
            await redis.hset(self._key("jobs"), job.id, json_dumps(job.to_dict()))
            return job
        # Job data missing — clean up
        await redis.zrem(self._key("pending"), job_id)
        return None

    async def requeue(self, job: Job) -> None:
        """Re-enqueue a job for retry."""
        redis = await self._get_redis()
        job.status = JobStatus.PENDING
        data = json_dumps(job.to_dict())
        await redis.hset(self._key("jobs"), job.id, data)
        if job.delay > 0:
            schedule_time = time.time() + job.delay
            await redis.zadd(self._key("delayed"), {job.id: schedule_time})
        else:
            await redis.zadd(self._key("pending"), {job.id: -job.priority})

    async def size(self) -> int:
        redis = await self._get_redis()
        return await redis.zcard(self._key("pending"))

    async def get_job(self, job_id: str) -> Optional[Job]:
        redis = await self._get_redis()
        data = await redis.hget(self._key("jobs"), job_id)
        if data:
            return Job.from_dict(json_loads(data))
        return None

    async def update_job(self, job: Job) -> None:
        redis = await self._get_redis()
        await redis.hset(self._key("jobs"), job.id, json_dumps(job.to_dict()))

    async def remove_job(self, job_id: str) -> bool:
        redis = await self._get_redis()
        existed = await redis.hdel(self._key("jobs"), job_id)
        await redis.zrem(self._key("pending"), job_id)
        await redis.zrem(self._key("delayed"), job_id)
        return existed > 0

    async def get_jobs_by_status(self, status: JobStatus) -> List[Job]:
        redis = await self._get_redis()
        all_data = await redis.hgetall(self._key("jobs"))
        result = []
        for data in all_data.values():
            job = Job.from_dict(json_loads(data))
            if job.status == status:
                result.append(job)
        return result

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None

    async def __aenter__(self) -> "RedisQueue":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()


class Queue:
    """High-level queue interface with handler registration.

    Usage::

        queue = Queue()

        @queue.handler("send_email")
        async def send_email(to: str, subject: str):
            ...

        await queue.enqueue("send_email", to="user@example.com", subject="Hello")
    """

    def __init__(self, backend: Optional[QueueBackend] = None) -> None:
        self._backend = backend or MemoryQueue()
        self._handlers: Dict[str, Callable] = {}

    @property
    def backend(self) -> QueueBackend:
        return self._backend

    def handler(self, name: Optional[str] = None) -> Callable:
        """Decorator to register a job handler."""
        def decorator(func: Callable) -> Callable:
            handler_name = name or f"{func.__module__}.{func.__qualname__}"
            self._handlers[handler_name] = func
            func._queue_name = handler_name
            return func
        return decorator

    def register(self, name: str, func: Callable) -> None:
        """Register a handler function directly."""
        self._handlers[name] = func

    async def enqueue(
        self,
        handler: str,
        *args: Any,
        delay: float = 0,
        priority: int = 0,
        max_retries: int = 3,
        timeout: Optional[float] = None,
        **kwargs: Any,
    ) -> Job:
        """Enqueue a job."""
        job = Job(
            handler=handler,
            args=args,
            kwargs=kwargs,
            delay=delay,
            priority=priority,
            max_retries=max_retries,
            timeout=timeout,
        )
        await self._backend.enqueue(job)
        return job

    async def process_next(self) -> Optional[Job]:
        """Process the next job in the queue."""
        job = await self._backend.dequeue()
        if job is None:
            return None

        handler = self._handlers.get(job.handler)
        if handler is None:
            job.status = JobStatus.FAILED
            job.error = f"Handler not found: {job.handler}"
            job.completed_at = time.time()
            await self._backend.update_job(job)
            logger.error("No handler for job %s (handler=%s)", job.id, job.handler)
            return job

        job.status = JobStatus.RUNNING
        job.started_at = time.time()
        await self._backend.update_job(job)

        try:
            if asyncio.iscoroutinefunction(handler):
                if job.timeout:
                    result = await asyncio.wait_for(
                        handler(*job.args, **job.kwargs),
                        timeout=job.timeout,
                    )
                else:
                    result = await handler(*job.args, **job.kwargs)
            else:
                # For sync handlers, run in thread with optional timeout
                if job.timeout:
                    result = await asyncio.wait_for(
                        to_thread(handler, *job.args, **job.kwargs),
                        timeout=job.timeout,
                    )
                else:
                    result = await to_thread(handler, *job.args, **job.kwargs)

            job.result = result
            job.status = JobStatus.COMPLETED
            job.completed_at = time.time()
            logger.debug("Job %s completed", job.id)
        except asyncio.TimeoutError:
            job.status = JobStatus.FAILED
            job.error = f"Job timed out after {job.timeout}s"
            job.completed_at = time.time()
            logger.error("Job %s timed out", job.id)
        except Exception as e:
            job.retry_count += 1
            if job.retry_count <= job.max_retries:
                job.status = JobStatus.RETRY
                delay = min(2 ** job.retry_count, 60)
                job.delay = delay
                logger.warning(
                    "Job %s failed (retry %d/%d in %.1fs): %s",
                    job.id, job.retry_count, job.max_retries, delay, e,
                )
                # Schedule retry without blocking the worker
                await self._backend.requeue(job)
            else:
                job.status = JobStatus.FAILED
                job.error = str(e)
                job.completed_at = time.time()
                logger.error("Job %s failed permanently: %s", job.id, e)

        await self._backend.update_job(job)
        return job

    async def get_job(self, job_id: str) -> Optional[Job]:
        return await self._backend.get_job(job_id)

    async def size(self) -> int:
        return await self._backend.size()

    async def cancel(self, job_id: str) -> bool:
        job = await self._backend.get_job(job_id)
        if job and job.status in (JobStatus.PENDING, JobStatus.RETRY):
            job.status = JobStatus.CANCELLED
            await self._backend.update_job(job)
            # Remove from pending queue if possible
            if hasattr(self._backend, 'remove_job'):
                await self._backend.remove_job(job_id)
            return True
        return False


class Worker:
    """Background worker that processes jobs from a queue.

    Usage::

        queue = Queue()
        worker = Worker(queue, concurrency=4)

        # Start in background
        asyncio.create_task(worker.start())

        # Or run until stopped
        await worker.run()
    """

    def __init__(
        self,
        queue: Queue,
        concurrency: int = 1,
        poll_interval: float = 0.1,
        max_jobs: Optional[int] = None,
    ) -> None:
        self._queue = queue
        self._concurrency = concurrency
        self._poll_interval = poll_interval
        self._max_jobs = max_jobs
        self._running = False
        self._tasks: List[asyncio.Task] = []
        self._jobs_processed = 0

    async def start(self) -> None:
        """Start the worker (non-blocking, creates background tasks)."""
        self._running = True
        for i in range(self._concurrency):
            task = asyncio.create_task(self._worker_loop(i))
            self._tasks.append(task)
        logger.info("Started worker with %d processors", self._concurrency)

    async def stop(self) -> None:
        """Stop the worker gracefully."""
        self._running = False
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        logger.info("Worker stopped. Processed %d jobs.", self._jobs_processed)

    async def run(self) -> None:
        """Run the worker until stopped (blocking)."""
        await self.start()
        try:
            while self._running:
                if self._max_jobs and self._jobs_processed >= self._max_jobs:
                    break
                await asyncio.sleep(self._poll_interval)
        except asyncio.CancelledError:
            pass
        finally:
            await self.stop()

    async def _worker_loop(self, worker_id: int) -> None:
        while self._running:
            try:
                if self._max_jobs and self._jobs_processed >= self._max_jobs:
                    break

                job = await self._queue.process_next()
                if job:
                    self._jobs_processed += 1
                else:
                    await asyncio.sleep(self._poll_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception("Worker %d error: %s", worker_id, e)
                await asyncio.sleep(1)
