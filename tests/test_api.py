"""Tests for the embedded 2N HAPI client."""

from __future__ import annotations

import asyncio
from importlib import import_module
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import respx

_api = import_module("custom_components.2n_intercom.hapi.api")
TwoNApiClient = _api.TwoNApiClient
_exceptions = import_module("custom_components.2n_intercom.hapi.exceptions")
TwoNApiError = _exceptions.TwoNApiError
TwoNAuthError = _exceptions.TwoNAuthError
TwoNConnectionError = _exceptions.TwoNConnectionError
TwoNNotSupportedError = _exceptions.TwoNNotSupportedError
TwoNPrivilegeError = _exceptions.TwoNPrivilegeError


BASE = "https://device.local"


@pytest.fixture
async def client() -> TwoNApiClient:
    """Return a client with a real httpx client (intercepted by respx)."""
    return TwoNApiClient(
        host=BASE,
        username="user",
        password="pass",
        client=httpx.AsyncClient(),
    )


@respx.mock
async def test_get_system_info(client: TwoNApiClient) -> None:
    """System info parses the documented fields."""
    respx.get(f"{BASE}/api/system/info").respond(
        json={
            "success": True,
            "result": {
                "variant": "2N IP Verso",
                "serialNumber": "00-0000-0005",
                "macAddr": "FC-1E-B3-00-00-05",
                "hwVersion": "570v1",
                "swVersion": "2.50.0.60.0",
                "buildType": "",
                "deviceName": "Front Door",
            },
        }
    )
    info = await client.get_system_info()
    assert info.variant == "2N IP Verso"
    assert info.serial_number == "00-0000-0005"
    assert info.device_name == "Front Door"
    assert info.mac_addr == "FC-1E-B3-00-00-05"


@respx.mock
async def test_error_envelope_mapping(client: TwoNApiClient) -> None:
    """Device error codes map to the correct exceptions."""
    route = respx.get(f"{BASE}/api/switch/caps")

    route.respond(
        json={
            "success": False,
            "error": {"code": 4, "description": "function is disabled"},
        }
    )
    with pytest.raises(TwoNNotSupportedError):
        await client.get_switch_caps()

    route.respond(
        json={
            "success": False,
            "error": {"code": 10, "description": "insufficient user privileges"},
        }
    )
    with pytest.raises(TwoNPrivilegeError):
        await client.get_switch_caps()

    route.respond(
        json={
            "success": False,
            "error": {
                "code": 12,
                "param": "switch",
                "description": "invalid parameter value",
            },
        }
    )
    with pytest.raises(TwoNApiError) as excinfo:
        await client.get_switch_caps()
    assert excinfo.value.code == 12
    assert excinfo.value.param == "switch"


@respx.mock
async def test_basic_auth_fallback(client: TwoNApiClient) -> None:
    """A Basic challenge is answered with Basic credentials."""
    route = respx.get(f"{BASE}/api/system/status")
    route.side_effect = [
        httpx.Response(401, headers={"WWW-Authenticate": 'Basic realm="2N"'}),
        httpx.Response(
            200,
            json={
                "success": True,
                "result": {"systemTime": 1752192000, "upTime": 100},
            },
        ),
    ]
    status = await client.get_system_status()
    assert status.up_time == 100
    # The second request carries Basic credentials.
    auth_header = route.calls[1].request.headers["Authorization"]
    assert auth_header.startswith("Basic ")


@respx.mock
async def test_auth_failure_raises(client: TwoNApiClient) -> None:
    """Persistent 401 raises TwoNAuthError."""
    respx.get(f"{BASE}/api/system/status").respond(
        401, headers={"WWW-Authenticate": 'Basic realm="2N"'}
    )
    with pytest.raises(TwoNAuthError):
        await client.get_system_status()


@respx.mock
async def test_privilege_error_from_403(client: TwoNApiClient) -> None:
    """HTTP 403 raises TwoNPrivilegeError."""
    respx.get(f"{BASE}/api/system/status").respond(403)
    with pytest.raises(TwoNPrivilegeError):
        await client.get_system_status()


@respx.mock
async def test_connection_error(client: TwoNApiClient) -> None:
    """Transport errors raise TwoNConnectionError."""
    respx.get(f"{BASE}/api/system/status").side_effect = httpx.ConnectError("refused")
    with pytest.raises(TwoNConnectionError):
        await client.get_system_status()


@respx.mock
async def test_call_status_enveloped(client: TwoNApiClient) -> None:
    """Older firmware wraps sessions in the standard envelope."""
    respx.get(f"{BASE}/api/call/status").respond(
        json={
            "success": True,
            "result": {
                "sessions": [
                    {"session": 1, "direction": "incoming", "state": "ringing"}
                ]
            },
        }
    )
    sessions = await client.get_call_status()
    assert len(sessions) == 1
    assert sessions[0].state == "ringing"


@respx.mock
async def test_call_status_bare_array(client: TwoNApiClient) -> None:
    """v2.50 firmware returns a bare JSON array."""
    respx.get(f"{BASE}/api/call/status").respond(
        json=[
            {
                "calls": [{"id": 6, "peer": "sip:10.0.29.27", "state": "ringing"}],
                "direction": "outgoing",
                "session": 4,
                "state": "ringing",
            }
        ]
    )
    sessions = await client.get_call_status()
    assert len(sessions) == 1
    assert sessions[0].session == 4
    assert sessions[0].peer == "sip:10.0.29.27"


@respx.mock
async def test_switch_ctrl_params(client: TwoNApiClient) -> None:
    """Switch control sends the documented query parameters."""
    route = respx.get(f"{BASE}/api/switch/ctrl").respond(json={"success": True})
    await client.set_switch(1, "trigger")
    params = route.calls[0].request.url.params
    assert params["switch"] == "1"
    assert params["action"] == "trigger"

    await client.set_switch(2, "hold", timeout=30)
    params = route.calls[1].request.url.params
    assert params["action"] == "hold"
    assert params["timeout"] == "30"


@respx.mock
async def test_log_subscribe_and_pull(client: TwoNApiClient) -> None:
    """Log subscription and event pulling parse the documented shapes."""
    respx.get(f"{BASE}/api/log/subscribe").respond(
        json={"success": True, "result": {"id": 2121013117}}
    )
    respx.get(f"{BASE}/api/log/pull").respond(
        json={
            "success": True,
            "result": {
                "events": [
                    {
                        "id": 1,
                        "tzShift": 0,
                        "utcTime": 1437987102,
                        "upTime": 8,
                        "event": "DeviceState",
                        "params": {"state": "startup"},
                    },
                    {
                        "id": 2,
                        "tzShift": 0,
                        "utcTime": 1437987105,
                        "upTime": 11,
                        "event": "KeyPressed",
                        "params": {"key": "%1"},
                    },
                ]
            },
        }
    )
    subscription_id = await client.log_subscribe()
    assert subscription_id == 2121013117
    events = await client.log_pull(subscription_id)
    assert len(events) == 2
    assert events[0].event == "DeviceState"
    assert events[1].params["key"] == "%1"


@respx.mock
async def test_camera_snapshot(client: TwoNApiClient) -> None:
    """Snapshots return raw JPEG bytes; JSON errors raise."""
    respx.get(f"{BASE}/api/camera/snapshot").respond(
        content=b"\xff\xd8jpegdata", content_type="image/jpeg"
    )
    image = await client.get_camera_snapshot(width=640, height=480)
    assert image.startswith(b"\xff\xd8")


@respx.mock
async def test_camera_snapshot_error(client: TwoNApiClient) -> None:
    """A JSON error body raises instead of returning bytes."""
    respx.get(f"{BASE}/api/camera/snapshot").respond(
        json={
            "success": False,
            "error": {"code": 12, "param": "width", "description": "invalid"},
        }
    )
    with pytest.raises(TwoNApiError):
        await client.get_camera_snapshot(width=123, height=456)


def _tolerant_client() -> TwoNApiClient:
    return TwoNApiClient(
        host=BASE,
        username="user",
        password="pass",
        client=httpx.AsyncClient(),
        tolerate_auth_failures=True,
    )


_UNAUTHORIZED = httpx.Response(401, headers={"WWW-Authenticate": 'Basic realm="2N"'})
_STATUS_OK = httpx.Response(
    200, json={"success": True, "result": {"systemTime": 1752192000, "upTime": 100}}
)


@respx.mock
async def test_single_401_then_success_is_not_auth_failure() -> None:
    """One refusal, then the same password works: no auth error."""
    client = _tolerant_client()
    respx.get(f"{BASE}/api/system/status").side_effect = [
        _UNAUTHORIZED,
        _UNAUTHORIZED,
        _STATUS_OK,
    ]
    # The first request gets 401 twice: once for Digest, once for Basic.
    with pytest.raises(TwoNConnectionError):
        await client.get_system_status()
    status = await client.get_system_status()
    assert status.up_time == 100


@respx.mock
async def test_repeated_401s_raise_auth_error() -> None:
    """A run of refusals over two minutes is a real auth failure."""
    client = _tolerant_client()
    respx.get(f"{BASE}/api/system/status").respond(
        401, headers={"WWW-Authenticate": 'Basic realm="2N"'}
    )
    clock = iter([0.0, 10.0, 20.0, 200.0])
    with patch.object(_api, "monotonic", side_effect=lambda: next(clock)):
        for _ in range(3):
            # Three refusals inside two minutes: still treated as transient.
            with pytest.raises(TwoNConnectionError):
                await client.get_system_status()
        with pytest.raises(TwoNAuthError):
            await client.get_system_status()


@respx.mock
async def test_success_resets_auth_failure_count() -> None:
    """A success between refusals starts the count again."""
    client = _tolerant_client()
    route = respx.get(f"{BASE}/api/system/status")
    clock = iter([0.0, 300.0, 600.0])
    with patch.object(_api, "monotonic", side_effect=lambda: next(clock)):
        route.side_effect = [_UNAUTHORIZED, _UNAUTHORIZED]
        with pytest.raises(TwoNConnectionError):
            await client.get_system_status()
        route.side_effect = [_UNAUTHORIZED, _STATUS_OK]
        await client.get_system_status()
        for _ in range(2):
            route.side_effect = [_UNAUTHORIZED, _UNAUTHORIZED]
            with pytest.raises(TwoNConnectionError):
                await client.get_system_status()


@respx.mock
async def test_event_listener_survives_single_401() -> None:
    """The event listener retries after one refusal instead of asking for re-auth."""
    client = _tolerant_client()
    auth_callback = MagicMock()
    client.register_auth_error_callback(auth_callback)
    respx.get(f"{BASE}/api/log/subscribe").side_effect = [
        _UNAUTHORIZED,
        _UNAUTHORIZED,
        httpx.Response(200, json={"success": True, "result": {"id": 7}}),
    ]
    respx.get(f"{BASE}/api/log/unsubscribe").respond(json={"success": True})
    # Reaching the pull means the listener subscribed; stop there.
    with (
        patch.object(client, "log_pull", AsyncMock(side_effect=asyncio.CancelledError)),
        patch.object(_api.asyncio, "sleep", AsyncMock()),
        pytest.raises(asyncio.CancelledError),
    ):
        await client._event_loop()
    auth_callback.assert_not_called()


@respx.mock
async def test_event_listener_reauths_after_repeated_401s() -> None:
    """The event listener asks for re-auth once refusals persist."""
    client = _tolerant_client()
    auth_callback = MagicMock()
    client.register_auth_error_callback(auth_callback)
    respx.get(f"{BASE}/api/log/subscribe").respond(
        401, headers={"WWW-Authenticate": 'Basic realm="2N"'}
    )
    clock = iter([0.0, 10.0, 20.0, 200.0])
    with (
        patch.object(_api, "monotonic", side_effect=lambda: next(clock)),
        patch.object(_api.asyncio, "sleep", AsyncMock()),
    ):
        await client._event_loop()
    auth_callback.assert_called_once()
