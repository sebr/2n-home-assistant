"""Tests for the 2N Intercom config flow."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.two_n_intercom.const import DOMAIN
from custom_components.two_n_intercom.hapi.exceptions import (
    TwoNAuthError,
    TwoNConnectionError,
)


@pytest.fixture
def flow_api(mock_api: MagicMock) -> Any:
    """Patch the config flow's API client construction."""
    with patch(
        "custom_components.two_n_intercom.config_flow.TwoNApiClient",
        return_value=mock_api,
    ):
        yield mock_api


USER_INPUT = {
    "host": "192.168.1.10",
    "username": "hapi",
    "password": "secret",
    "verify_ssl": False,
}


async def test_user_flow_success(
    hass: HomeAssistant, flow_api: MagicMock, patch_api: MagicMock
) -> None:
    """A successful flow creates an entry titled after the device."""
    # Entry creation triggers a real async_setup_entry, so the coordinator's
    # own client construction (patch_api) needs mocking too, not just flow_api.
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input=USER_INPUT
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Front Door"
    # Scheme is prepended automatically.
    assert result["data"]["host"] == "https://192.168.1.10"
    assert result["result"].unique_id == "00-0000-0005"


async def test_user_flow_invalid_auth(hass: HomeAssistant, flow_api: MagicMock) -> None:
    """Bad credentials show an inline error and allow retry."""
    flow_api.get_system_info.side_effect = TwoNAuthError("bad credentials")

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input=USER_INPUT
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_user_flow_cannot_connect(
    hass: HomeAssistant, flow_api: MagicMock
) -> None:
    """Connection failures show an inline error."""
    flow_api.get_system_info.side_effect = TwoNConnectionError("timeout")

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input=USER_INPUT
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_user_flow_duplicate_aborts(
    hass: HomeAssistant, flow_api: MagicMock, mock_config_entry_data: dict[str, Any]
) -> None:
    """Configuring the same device twice aborts."""
    MockConfigEntry(
        domain=DOMAIN,
        data=mock_config_entry_data,
        unique_id="00-0000-0005",
    ).add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input=USER_INPUT
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_user_flow_duplicate_host_without_unique_id_aborts(
    hass: HomeAssistant, flow_api: MagicMock, mock_config_entry_data: dict[str, Any]
) -> None:
    """Without a serial/MAC, a matching host still blocks duplicates."""
    from dataclasses import replace

    flow_api.get_system_info.return_value = replace(
        flow_api.get_system_info.return_value,
        serial_number=None,
        mac_addr=None,
    )
    MockConfigEntry(domain=DOMAIN, data=mock_config_entry_data).add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input=USER_INPUT
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
