import asyncio
from uuid import UUID

import httpx

from services.api.app import app


def request(method, route, **kwargs):
    async def send():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            return await client.request(method, route, **kwargs)

    return asyncio.run(send())


def test_live_server_does_not_claim_inference_readiness():
    live = request("GET", "/health/live")
    ready = request("GET", "/health/ready")
    assert live.status_code == 200
    assert live.json()["status"] == "alive"
    assert ready.status_code == 503
    assert ready.json()["ready"] is False
    assert all(not capability["available"] for capability in ready.json()["capabilities"])


def test_translation_request_fails_explicitly_without_echoing_private_input():
    response = request("POST", "/v1/batches", json={"private_text": "secret-probe-not-for-output"})
    assert response.status_code == 503
    error = response.json()["error"]
    assert error["code"] == "MODEL_NOT_READY"
    assert error["retryable"] is False
    assert "secret-probe-not-for-output" not in response.text
    assert UUID(error["request_id"])
    assert response.headers["X-Request-ID"] == error["request_id"]
    assert response.headers["Cache-Control"] == "no-store"


def test_capabilities_do_not_offer_upload_or_billing():
    response = request("GET", "/v1/capabilities")
    assert response.json()["upload_enabled"] is False
    assert response.json()["billing_enabled"] is False
    assert request("POST", "/assets/upload-intents").status_code == 404


def test_arbitrary_web_origins_and_hostnames_are_not_granted_access():
    response = request("GET", "/health/live", headers={"Origin": "https://untrusted.example"})
    assert "access-control-allow-origin" not in response.headers
    assert request("GET", "/health/live", headers={"Host": "untrusted.example"}).status_code == 400
