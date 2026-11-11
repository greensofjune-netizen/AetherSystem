from __future__ import annotations

from threading import Event, Thread
from time import monotonic, sleep

import pytest

from aether_engine.inference_scheduler import (
    InferenceCapacityError,
    InferenceQueueTimeoutError,
    InferenceScheduler,
)


def _wait_for_queue(scheduler: InferenceScheduler, queued: int) -> None:
    deadline = monotonic() + 2
    while scheduler.snapshot().queued != queued and monotonic() < deadline:
        sleep(0.005)
    assert scheduler.snapshot().queued == queued


def test_scheduler_bounds_active_and_queued_work():
    scheduler = InferenceScheduler(1, 1, 1)
    release_first = Event()
    first_started = Event()
    second_started = Event()

    first = Thread(
        target=lambda: scheduler.run(
            lambda: (first_started.set(), release_first.wait(2))
        ),
        daemon=True,
    )
    second = Thread(
        target=lambda: scheduler.run(second_started.set),
        daemon=True,
    )
    first.start()
    assert first_started.wait(1)
    second.start()
    _wait_for_queue(scheduler, 1)

    with pytest.raises(InferenceCapacityError, match="capacity is full"):
        scheduler.run(lambda: None)

    release_first.set()
    first.join(timeout=1)
    second.join(timeout=1)
    assert not first.is_alive()
    assert not second.is_alive()
    assert second_started.is_set()
    assert scheduler.snapshot().active == 0
    assert scheduler.snapshot().queued == 0


def test_scheduler_times_out_queued_work_and_releases_capacity():
    scheduler = InferenceScheduler(1, 1, 0.05)
    release_first = Event()
    first_started = Event()

    first = Thread(
        target=lambda: scheduler.run(
            lambda: (first_started.set(), release_first.wait(2))
        ),
        daemon=True,
    )
    first.start()
    assert first_started.wait(1)
    with pytest.raises(InferenceQueueTimeoutError, match="wait exceeded"):
        scheduler.run(lambda: None)
    assert scheduler.snapshot().queued == 0

    release_first.set()
    first.join(timeout=1)
    assert not first.is_alive()
