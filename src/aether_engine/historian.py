from __future__ import annotations

from .database import AetherStore, Event


class CoPilotHistorian:
    def __init__(self, store: AetherStore) -> None:
        self.store = store

    def record(self, topic: str, message: str) -> Event:
        return self.store.add_event(topic, message)

    def history(
        self,
        limit: int = 20,
        *,
        search: str | None = None,
        topic: str | None = None,
        since: str | None = None,
        until: str | None = None,
    ) -> list[Event]:
        return self.store.list_events(
            limit, search=search, topic=topic, since=since, until=until
        )
