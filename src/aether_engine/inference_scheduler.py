from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from math import isfinite
from threading import BoundedSemaphore, Lock
from time import monotonic
from typing import TypeVar

ResultT = TypeVar("ResultT")


class InferenceCapacityError(RuntimeError):
    """Raised when the bounded inference queue has no available capacity."""


class InferenceQueueTimeoutError(RuntimeError):
    """Raised when an admitted inference cannot start before its deadline."""


class InferenceSchedulerClosedError(RuntimeError):
    """Raised when inference is requested after scheduler shutdown begins."""


@dataclass(frozen=True)
class SchedulerSnapshot:
    active: int
    queued: int
    capacity: int
    closed: bool


class InferenceScheduler:
    """Bound concurrent inference and queued work with an explicit deadline."""

    def __init__(
        self, max_concurrent: int, max_queued: int, queue_timeout_seconds: float
    ) -> None:
        if type(max_concurrent) is not int or max_concurrent < 1:
            raise ValueError("Inference concurrency must be at least one.")
        if type(max_queued) is not int or max_queued < 0:
            raise ValueError("Inference queue capacity cannot be negative.")
        if not isfinite(queue_timeout_seconds) or queue_timeout_seconds <= 0:
            raise ValueError("Inference queue timeout must be greater than zero.")
        self._active_slots = BoundedSemaphore(max_concurrent)
        self._admission_slots = BoundedSemaphore(max_concurrent + max_queued)
        self._lock = Lock()
        self._max_concurrent = max_concurrent
        self._max_queued = max_queued
        self._queue_timeout_seconds = queue_timeout_seconds
        self._active = 0
        self._queued = 0
        self._closed = False

    def run(self, operation: Callable[[], ResultT]) -> ResultT:
        with self._lock:
            if self._closed:
                raise InferenceSchedulerClosedError(
                    "Inference scheduler is shutting down."
                )
        if not self._admission_slots.acquire(blocking=False):
            raise InferenceCapacityError(
                "Inference capacity is full. Retry after an active request completes."
            )

        with self._lock:
            if self._closed:
                self._admission_slots.release()
                raise InferenceSchedulerClosedError(
                    "Inference scheduler is shutting down."
                )
            self._queued += 1

        active_acquired = False
        queued_registered = True
        active_registered = False
        try:
            deadline = monotonic() + self._queue_timeout_seconds
            while not active_acquired:
                with self._lock:
                    if self._closed:
                        raise InferenceSchedulerClosedError(
                            "Inference scheduler is shutting down."
                        )
                remaining = deadline - monotonic()
                if remaining <= 0:
                    raise InferenceQueueTimeoutError(
                        "Inference queue wait exceeded its time limit."
                    )
                active_acquired = self._active_slots.acquire(
                    timeout=min(remaining, 0.1)
                )

            with self._lock:
                if self._closed:
                    raise InferenceSchedulerClosedError(
                        "Inference scheduler is shutting down."
                    )
                self._queued -= 1
                queued_registered = False
                self._active += 1
                active_registered = True
            return operation()
        finally:
            with self._lock:
                if queued_registered:
                    self._queued -= 1
                if active_registered:
                    self._active -= 1
            if active_acquired:
                self._active_slots.release()
            self._admission_slots.release()

    def close(self) -> None:
        with self._lock:
            self._closed = True

    def snapshot(self) -> SchedulerSnapshot:
        with self._lock:
            return SchedulerSnapshot(
                active=self._active,
                queued=self._queued,
                capacity=self._max_concurrent + self._max_queued,
                closed=self._closed,
            )
