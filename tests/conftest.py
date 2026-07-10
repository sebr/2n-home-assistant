"""Global test configuration for the 2N Intercom integration tests."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.two_n_intercom.hapi.api import TwoNApiClient
from custom_components.two_n_intercom.hapi.models import (
    CallSession,
    CameraCaps,
    IoPort,
    IoPortStatus,
    PhoneAccount,
    SwitchCaps,
    SwitchStatus,
    SystemInfo,
    SystemStatus,
)

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: Any) -> None:
    """Enable loading custom integrations in all tests."""
    return


@pytest.fixture
def mock_config_entry_data() -> dict[str, Any]:
    """Return mock config entry data."""
    return {
        "host": "https://192.168.1.10",
        "username": "hapi",
        "password": "secret",
        "verify_ssl": False,
    }


SYSTEM_INFO = SystemInfo(
    variant="2N IP Verso",
    serial_number="00-0000-0005",
    hw_version="570v1",
    sw_version="2.50.0.60.0",
    build_type="",
    device_name="Front Door",
    mac_addr="FC-1E-B3-00-00-05",
    raw={"serialNumber": "00-0000-0005"},
)


@pytest.fixture
def mock_api() -> MagicMock:
    """Return a fully-stubbed TwoNApiClient."""
    api = MagicMock(spec=TwoNApiClient)
    api.host = "https://192.168.1.10"
    api.get_system_info = AsyncMock(return_value=SYSTEM_INFO)
    api.get_system_caps = AsyncMock(
        return_value={"camera": "active", "switches": "active"}
    )
    api.get_system_status = AsyncMock(
        return_value=SystemStatus(system_time=1752192000, up_time=3600)
    )
    api.get_switch_caps = AsyncMock(
        return_value=[
            SwitchCaps(
                switch=1,
                enabled=True,
                mode="monostable",
                switch_on_duration=5,
                type="normal",
            ),
            SwitchCaps(switch=2, enabled=False),
        ]
    )
    api.get_switch_status = AsyncMock(
        return_value=[SwitchStatus(switch=1, active=False, locked=False, held=False)]
    )
    api.set_switch = AsyncMock()
    api.get_io_caps = AsyncMock(
        return_value=[
            IoPort(port="relay1", type="output"),
            IoPort(port="input1", type="input"),
        ]
    )
    api.get_io_status = AsyncMock(
        return_value=[
            IoPortStatus(port="relay1", state=0),
            IoPortStatus(port="input1", state=1),
        ]
    )
    api.set_io = AsyncMock()
    api.get_camera_caps = AsyncMock(
        return_value=CameraCaps(
            jpeg_resolutions=[(160, 120), (640, 480)], sources=["internal"]
        )
    )
    api.get_camera_snapshot = AsyncMock(return_value=b"\xff\xd8fakejpeg")
    api.get_call_status = AsyncMock(return_value=[])
    api.dial = AsyncMock(return_value=2)
    api.answer_call = AsyncMock()
    api.hangup_call = AsyncMock()
    api.get_phone_status = AsyncMock(
        return_value=[
            PhoneAccount(
                account=1,
                account_type="general",
                enabled=True,
                sip_number="100",
                registration_enabled=True,
                registered=True,
                register_time=1752190000,
            )
        ]
    )
    api.audio_test = AsyncMock()
    api.restart = AsyncMock()
    api.display_text = AsyncMock()
    api.automation_trigger = AsyncMock()
    api.get_log_caps = AsyncMock(
        return_value=[
            "KeyPressed",
            "CardEntered",
            "MotionDetected",
            "SwitchStateChanged",
            "CallStateChanged",
            "UserAuthenticated",
        ]
    )
    api.register_event_callback = MagicMock()
    api.register_auth_error_callback = MagicMock()
    api.start_event_listener = MagicMock()
    api.stop_event_listener = AsyncMock()
    api.close = AsyncMock()
    return api


@pytest.fixture
def patch_api(mock_api: MagicMock) -> Any:
    """Patch the coordinator's API client construction."""
    with patch(
        "custom_components.two_n_intercom.coordinator.TwoNApiClient",
        return_value=mock_api,
    ):
        yield mock_api


def make_call_session(state: str = "ringing") -> CallSession:
    """Return a call session in the given state."""
    return CallSession.from_dict(
        {
            "session": 1,
            "direction": "incoming",
            "state": state,
            "calls": [{"id": 1, "peer": "sip:100@10.0.0.1", "state": state}],
        }
    )
