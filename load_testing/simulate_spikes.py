import asyncio
import random
import time
from dataclasses import dataclass

import httpx

TARGET_STREAM_URL = "http://127.0.0.1:8000/api/v1/dashboard/stream"
TARGET_SNAPSHOT_URL = "http://127.0.0.1:8000/api/v1/dashboard/snapshot"
SIMULATED_CLIENTS = 15
SNAPSHOT_REQUESTS_PER_CLIENT = 20


@dataclass
class SimulationStats:
    successful_snapshots: int = 0
    failed_snapshots: int = 0
    active_streams: int = 0
    stream_errors: int = 0


async def flood_snapshot_requests(client_id: int, stats: SimulationStats) -> None:
    """Simulate a frontend tab polling the local snapshot route."""
    async with httpx.AsyncClient() as client:
        headers = {"Host": "127.0.0.1:8000"}
        for _ in range(SNAPSHOT_REQUESTS_PER_CLIENT):
            try:
                response = await client.get(
                    TARGET_SNAPSHOT_URL,
                    headers=headers,
                    timeout=1.0,
                )
                if response.is_success:
                    stats.successful_snapshots += 1
                else:
                    stats.failed_snapshots += 1
                    print(
                        f"Snapshot request from client {client_id} "
                        f"returned HTTP {response.status_code}."
                    )
            except httpx.HTTPError as error:
                stats.failed_snapshots += 1
                print(f"Snapshot request from client {client_id} failed: {error}")

            await asyncio.sleep(random.uniform(0.05, 0.2))


async def listen_to_live_stream(client_id: int, stats: SimulationStats) -> None:
    """Simulate a UI panel briefly listening to the local SSE stream."""
    async with httpx.AsyncClient() as client:
        headers = {"Host": "127.0.0.1:8000"}
        try:
            async with client.stream(
                "GET",
                TARGET_STREAM_URL,
                headers=headers,
                timeout=4.0,
            ) as response:
                if response.status_code != 200:
                    stats.stream_errors += 1
                    print(
                        f"Stream for client {client_id} returned "
                        f"HTTP {response.status_code}."
                    )
                    return

                stats.active_streams += 1
                async for line in response.aiter_lines():
                    if line and random.random() < 0.15:
                        break
        except httpx.HTTPError as error:
            stats.stream_errors += 1
            print(f"Stream for client {client_id} failed: {error}")


async def main() -> None:
    print("Initializing local high-frequency processing spike simulator...")
    print(
        f"Spawning {SIMULATED_CLIENTS} concurrent snapshot pollers "
        "and live streams..."
    )

    start_time = time.time()
    stats = SimulationStats()
    workers = []
    for client_id in range(SIMULATED_CLIENTS):
        workers.append(flood_snapshot_requests(client_id, stats))
        workers.append(listen_to_live_stream(client_id, stats))

    await asyncio.gather(*workers)
    elapsed = round(time.time() - start_time, 2)
    print(f"Spike simulation concluded in {elapsed}s.")
    print(
        f"Snapshot requests: {stats.successful_snapshots} succeeded, "
        f"{stats.failed_snapshots} failed."
    )
    print(
        f"Streams: {stats.active_streams} connected, "
        f"{stats.stream_errors} failed."
    )
    print("Check the local server console for execution stability.")


if __name__ == "__main__":
    asyncio.run(main())
