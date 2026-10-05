"""Tests for the firmware update entity."""

from __future__ import annotations

from dataclasses import replace
from importlib import import_module
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.typing import WebSocketGenerator

from .conftest import SYSTEM_INFO

_const = import_module("custom_components.2n_intercom.const")
DOMAIN = _const.DOMAIN
_coordinator = import_module("custom_components.2n_intercom.coordinator")
_models = import_module("custom_components.2n_intercom.hapi.models")
ChangelogEntry = _models.ChangelogEntry
FirmwareRelease = _models.FirmwareRelease
_exceptions = import_module("custom_components.2n_intercom.hapi.exceptions")
TwoNConnectionError = _exceptions.TwoNConnectionError

INFO = replace(SYSTEM_INFO, sw_version="3.2.0.79.2", firmware_package="verso2")
NEWEST = FirmwareRelease(
    version="3.3.1.82.4",
    download_url="https://update.2n.cz/api/downloads/2bd41ee3",
    checksum="f54f0776",
    changelog=[
        ChangelogEntry(version="3.3.0.82.2", text="### 3.3.0"),
        ChangelogEntry(version="3.3.1.82.4", text="### 3.3.1"),
    ],
)


async def _setup(
    hass: HomeAssistant, entry_data: dict[str, Any], newest: AsyncMock
) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN, title="Front Door", data=entry_data, unique_id="00-0000-0005"
    )
    entry.add_to_hass(hass)
    with patch.object(_coordinator, "get_newest_firmware", newest):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


def _entity_id(hass: HomeAssistant, entry: MockConfigEntry) -> str | None:
    return er.async_get(hass).async_get_entity_id(
        "update", DOMAIN, f"{entry.entry_id}_firmware"
    )


@pytest.fixture
def firmware_api(patch_api: MagicMock) -> MagicMock:
    """Make the mock device report a firmware package."""
    patch_api.get_system_info = AsyncMock(return_value=INFO)
    return patch_api


@pytest.mark.usefixtures("firmware_api")
async def test_update_available(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
    mock_config_entry_data: dict[str, Any],
) -> None:
    """Newer firmware turns the entity on and exposes release notes."""
    entry = await _setup(hass, mock_config_entry_data, AsyncMock(return_value=NEWEST))
    entity_id = _entity_id(hass, entry)
    state = hass.states.get(entity_id)
    assert state.state == STATE_ON
    assert state.attributes["installed_version"] == "3.2.0.79.2"
    assert state.attributes["latest_version"] == "3.3.1.82.4"
    assert state.attributes["title"] == "2N OS"

    client = await hass_ws_client(hass)
    await client.send_json(
        {"id": 1, "type": "update/release_notes", "entity_id": entity_id}
    )
    result = await client.receive_json()
    assert result["result"] == "### 3.3.1\n\n### 3.3.0"


@pytest.mark.usefixtures("firmware_api")
async def test_up_to_date(
    hass: HomeAssistant, mock_config_entry_data: dict[str, Any]
) -> None:
    """No newer firmware leaves the entity off."""
    entry = await _setup(hass, mock_config_entry_data, AsyncMock(return_value=None))
    state = hass.states.get(_entity_id(hass, entry))
    assert state.state == STATE_OFF
    assert state.attributes["latest_version"] == "3.2.0.79.2"


@pytest.mark.usefixtures("firmware_api")
async def test_check_fails(
    hass: HomeAssistant, mock_config_entry_data: dict[str, Any]
) -> None:
    """A failed check doesn't block setup; the entity is unavailable."""
    entry = await _setup(
        hass,
        mock_config_entry_data,
        AsyncMock(side_effect=TwoNConnectionError("offline")),
    )
    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.get(_entity_id(hass, entry)).state == STATE_UNAVAILABLE


@pytest.mark.usefixtures("patch_api")
async def test_no_firmware_package(
    hass: HomeAssistant, mock_config_entry_data: dict[str, Any]
) -> None:
    """Devices that don't report a firmware package get no update entity."""
    newest = AsyncMock()
    entry = await _setup(hass, mock_config_entry_data, newest)
    assert _entity_id(hass, entry) is None
    newest.assert_not_called()
