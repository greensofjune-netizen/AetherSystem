import asyncio
import json

import pytest

import live_sync_supervisor


def test_cloud_cover_alerts_only_broadcast_on_threshold_transitions() -> None:
    async def check() -> None:
        supervisor = live_sync_supervisor.LiveSyncSupervisor()
        queue = supervisor.register_interface()

        await supervisor.evaluate_cloud_cover_alerts(
            {"cloud_cover": 15, "city": "Upland", "is_live": True}
        )
        clear_alert = json.loads(queue.get_nowait())
        assert clear_alert["event"] == "CONSOLE_ALERT"
        assert clear_alert["data"] == {
            "message": (
                "☀️ Clear Skies in Upland: Cloud cover dropped to 15% "
                "(Optimal visibility/solar)."
            ),
            "severity": "INFO",
            "cloud_cover": 15,
            "city": "Upland",
        }

        await supervisor.evaluate_cloud_cover_alerts(
            {"cloud_cover": 10, "city": "Upland", "is_live": True}
        )
        assert queue.empty()

        await supervisor.evaluate_cloud_cover_alerts(
            {"cloud_cover": 50, "city": "Upland", "is_live": True}
        )
        await supervisor.evaluate_cloud_cover_alerts(
            {"cloud_cover": 85, "city": "Upland", "is_live": True}
        )
        overcast_alert = json.loads(queue.get_nowait())
        assert overcast_alert["data"]["severity"] == "WARNING"
        assert overcast_alert["data"]["cloud_cover"] == 85
        assert overcast_alert["data"]["city"] == "Upland"
        assert "Heavy Cloud Cover" in overcast_alert["data"]["message"]

        await supervisor.evaluate_cloud_cover_alerts(
            {"cloud_cover": 100, "city": "Upland", "is_live": True}
        )
        assert queue.empty()
        supervisor.unregister_interface(queue)

    asyncio.run(check())


def test_cloud_cover_alerts_ignore_missing_or_stale_readings() -> None:
    async def check() -> None:
        supervisor = live_sync_supervisor.LiveSyncSupervisor()
        queue = supervisor.register_interface()

        await supervisor.evaluate_cloud_cover_alerts(
            {"cloud_cover": 5, "city": "Upland", "is_live": False}
        )
        await supervisor.evaluate_cloud_cover_alerts({"city": "Upland", "is_live": True})

        assert queue.empty()
        assert supervisor._last_cloud_alert_state is None

    asyncio.run(check())


@pytest.mark.parametrize(
    "cloud_cover",
    [-1, 101, 10**400, float("nan"), float("inf"), True, "15"],
)
def test_cloud_cover_alerts_reject_invalid_live_percentages(cloud_cover) -> None:
    async def check() -> None:
        supervisor = live_sync_supervisor.LiveSyncSupervisor()
        with pytest.raises(ValueError, match="finite percentage"):
            await supervisor.evaluate_cloud_cover_alerts(
                {"cloud_cover": cloud_cover, "is_live": True}
            )

    asyncio.run(check())


def test_module_cloud_cover_helper_uses_shared_supervisor(monkeypatch) -> None:
    async def check() -> None:
        supervisor = live_sync_supervisor.LiveSyncSupervisor()
        queue = supervisor.register_interface()
        monkeypatch.setattr(live_sync_supervisor, "supervisor", supervisor)

        await live_sync_supervisor.evaluate_cloud_cover_alerts(
            {"cloud_cover": 90, "is_live": True}
        )

        alert = json.loads(queue.get_nowait())
        assert alert["event"] == "CONSOLE_ALERT"
        assert alert["data"]["city"] == "Unknown Location"
        assert alert["data"]["severity"] == "WARNING"

    asyncio.run(check())


def test_broadcast_disconnects_slow_subscriber(monkeypatch) -> None:
    async def check() -> None:
        monkeypatch.setattr(
            live_sync_supervisor, "MAX_PENDING_EVENTS_PER_INTERFACE", 1
        )
        supervisor = live_sync_supervisor.LiveSyncSupervisor()
        queue = supervisor.register_interface()

        assert await supervisor.broadcast("FIRST", {}) == 1
        assert await supervisor.broadcast("SECOND", {}) == 0
        assert queue.get_nowait() is None
        assert not supervisor._connected_interfaces

    asyncio.run(check())


def test_register_interface_enforces_subscriber_limit(monkeypatch) -> None:
    monkeypatch.setattr(live_sync_supervisor, "MAX_CONNECTED_INTERFACES", 1)
    supervisor = live_sync_supervisor.LiveSyncSupervisor()
    supervisor.register_interface()

    with pytest.raises(RuntimeError, match="subscriber limit"):
        supervisor.register_interface()
