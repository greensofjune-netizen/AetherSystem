from __future__ import annotations

import asyncio

import httpx

from app import app, my_custom_logic


def _get_process(**params: str) -> httpx.Response:
    async def send_request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            return await client.get("/process", params=params)

    return asyncio.run(send_request())


def test_custom_logic_trims_input() -> None:
    assert my_custom_logic("  hello  ") == {"result": "Processed: hello"}


def test_process_endpoint_returns_processed_input() -> None:
    response = _get_process(input_data="hello world")

    assert response.status_code == 200
    assert response.json() == {"result": "Processed: hello world"}


def test_process_endpoint_rejects_blank_input() -> None:
    response = _get_process(input_data="   ")

    assert response.status_code == 422
    assert response.json()["detail"] == "Input cannot be blank."


def test_process_endpoint_requires_input() -> None:
    response = _get_process()

    assert response.status_code == 422
