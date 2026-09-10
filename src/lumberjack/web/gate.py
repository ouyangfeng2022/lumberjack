"""Concurrency gate for split worker threads.

A plain capacity limiter releases its slot the moment a timed-out request is
abandoned, which lets abandoned worker threads accumulate beyond the
configured concurrency limit. This gate hands out leases that are released by
the worker thread itself when the split actually finishes, so a timed-out
(zombie) worker keeps occupying its slot until it drains and the configured
limit stays truthful.
"""

from __future__ import annotations

import asyncio
import contextlib
import itertools
import threading

_RELEASE_LOCK = threading.Lock()


class SplitExecutionGate:
    """Bounds concurrently running split threads with worker-side release."""

    def __init__(self, limit: int) -> None:
        if limit <= 0:
            raise ValueError("limit must be positive")
        self._limit = limit
        self._slots = asyncio.Semaphore(limit)
        self._active: set[int] = set()
        self._lease_ids = itertools.count()
        self._loop: asyncio.AbstractEventLoop | None = None

    @property
    def limit(self) -> int:
        return self._limit

    @property
    def running(self) -> int:
        """Number of leases currently held (running or abandoned workers)."""
        return len(self._active)

    async def acquire(self) -> int:
        """Wait for a free slot and return the lease handle."""
        self._loop = asyncio.get_running_loop()
        await self._slots.acquire()
        lease = next(self._lease_ids)
        self._active.add(lease)
        return lease

    def release(self, lease: int) -> None:
        """Release a lease; idempotent and callable from any thread.

        The second release of the same lease is a no-op, which covers the
        race between a request task releasing inline and its worker thread
        releasing from the ``finally`` block.
        """
        with _RELEASE_LOCK:
            if lease not in self._active:
                return
            self._active.discard(lease)
        loop = self._loop
        if loop is None:
            return
        # The owning event loop may already have shut down (the app is gone
        # and there is nothing left to wake up), in which case
        # call_soon_threadsafe raises RuntimeError.
        with contextlib.suppress(RuntimeError):
            loop.call_soon_threadsafe(self._slots.release)


__all__ = ["SplitExecutionGate"]
