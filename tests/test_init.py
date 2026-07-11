"""Tests for integration setup, entities and event handling."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.two_n_intercom.const import DOMAIN, EVENT_TWO_N_EVENT
from custom_components.two_n_intercom.hapi.models import TwoNEvent

from .conftest import make_call_session


@pytest.fixture
async def setup_entry(
    hass: HomeAssistant,
    patch_api: MagicMock,
    mock_config_entry_data: dict[str, Any],
) -> MockConfigEntry:
    """Set up a config entry backed by the mock API."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Front Door",
        data=mock_config_entry_data,
        unique_id="00-0000-0005",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_setup_and_unload(
    hass: HomeAssistant, setup_entry: MockConfigEntry, patch_api: MagicMock
) -> None:
    """The entry loads, starts the event listener, and unloads cleanly."""
    assert setup_entry.state is ConfigEntryState.LOADED
    patch_api.start_event_listener.assert_called_once()

    assert await hass.config_entries.async_unload(setup_entry.entry_id)
    await hass.async_block_till_done()
    assert setup_entry.state is ConfigEntryState.NOT_LOADED
    patch_api.close.assert_called()


async def test_entities_created(
    hass: HomeAssistant, setup_entry: MockConfigEntry
) -> None:
    """Capability discovery creates the expected entities."""
    registry = er.async_get(hass)
    unique_ids = {
        entity.unique_id
        for entity in registry.entities.values()
        if entity.config_entry_id == setup_entry.entry_id
    }
    prefix = setup_entry.entry_id
    expected = {
        f"{prefix}_switch_1",  # enabled switch
        f"{prefix}_io_relay1",  # output port
        f"{prefix}_io_input1",  # input port
        f"{prefix}_lock_1",  # door lock for switch 1
        f"{prefix}_switch_trigger_1",
        f"{prefix}_restart",
        f"{prefix}_camera",
        f"{prefix}_motion",  # MotionDetected in log caps
        f"{prefix}_call_in_progress",
        f"{prefix}_ringing",
        f"{prefix}_sip_1",
        f"{prefix}_last_restart",
        f"{prefix}_call_state",
        f"{prefix}_doorbell",
        f"{prefix}_keypad",
        f"{prefix}_access",
        f"{prefix}_call",
        f"{prefix}_last_card",
        f"{prefix}_last_user",
        f"{prefix}_last_key",
    }
    assert expected <= unique_ids
    # Switch 2 is disabled on the device and must not create entities.
    assert f"{prefix}_switch_2" not in unique_ids

    # Sanity-check a few states.
    switch_entity = registry.async_get_entity_id("switch", DOMAIN, f"{prefix}_switch_1")
    assert hass.states.get(switch_entity).state == "off"
    lock_entity = registry.async_get_entity_id("lock", DOMAIN, f"{prefix}_lock_1")
    assert hass.states.get(lock_entity).state == "locked"

    # Privacy-sensitive and niche entities are registered but disabled by
    # default, so they have no state until a user opts in.
    for key in ("keypad", "last_card", "last_user", "last_key", "io_input1", "sip_1"):
        entry = registry.async_get(
            registry.async_get_entity_id("binary_sensor", DOMAIN, f"{prefix}_{key}")
            or registry.async_get_entity_id("sensor", DOMAIN, f"{prefix}_{key}")
            or registry.async_get_entity_id("event", DOMAIN, f"{prefix}_{key}")
        )
        assert entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION

    # The redundant call binary sensors stay enabled but hidden from dashboards.
    ringing_entry = registry.async_get(
        registry.async_get_entity_id("binary_sensor", DOMAIN, f"{prefix}_ringing")
    )
    assert ringing_entry.disabled_by is None
    assert ringing_entry.hidden_by is er.RegistryEntryHider.INTEGRATION


async def test_device_event_fires_bus_and_updates_state(
    hass: HomeAssistant, setup_entry: MockConfigEntry, patch_api: MagicMock
) -> None:
    """A pulled device event fires a bus event and updates entities."""
    coordinator = setup_entry.runtime_data
    event_callback = patch_api.register_event_callback.call_args[0][0]

    bus_events = []
    hass.bus.async_listen(EVENT_TWO_N_EVENT, bus_events.append)

    event_callback(
        TwoNEvent(
            id=10,
            event="SwitchStateChanged",
            utc_time=1752192000,
            params={"switch": 1, "state": True},
        )
    )
    await hass.async_block_till_done()

    assert len(bus_events) == 1
    assert bus_events[0].data["event"] == "SwitchStateChanged"
    assert bus_events[0].data["params"] == {"switch": 1, "state": True}
    assert coordinator.data.switches[1].active is True

    registry = er.async_get(hass)
    prefix = setup_entry.entry_id
    switch_entity = registry.async_get_entity_id("switch", DOMAIN, f"{prefix}_switch_1")
    assert hass.states.get(switch_entity).state == "on"
    lock_entity = registry.async_get_entity_id("lock", DOMAIN, f"{prefix}_lock_1")
    assert hass.states.get(lock_entity).state == "unlocked"


async def test_motion_event_binary_sensor(
    hass: HomeAssistant, setup_entry: MockConfigEntry, patch_api: MagicMock
) -> None:
    """Motion events flip the motion binary sensor."""
    event_callback = patch_api.register_event_callback.call_args[0][0]
    registry = er.async_get(hass)
    motion_entity = registry.async_get_entity_id(
        "binary_sensor", DOMAIN, f"{setup_entry.entry_id}_motion"
    )
    assert hass.states.get(motion_entity).state == "unknown"

    event_callback(TwoNEvent(id=11, event="MotionDetected", params={"state": "in"}))
    await hass.async_block_till_done()
    assert hass.states.get(motion_entity).state == "on"

    event_callback(TwoNEvent(id=12, event="MotionDetected", params={"state": "out"}))
    await hass.async_block_till_done()
    assert hass.states.get(motion_entity).state == "off"


async def test_doorbell_event_entity(
    hass: HomeAssistant, setup_entry: MockConfigEntry, patch_api: MagicMock
) -> None:
    """A quick dial key press triggers the doorbell event entity."""
    event_callback = patch_api.register_event_callback.call_args[0][0]
    registry = er.async_get(hass)
    doorbell_entity = registry.async_get_entity_id(
        "event", DOMAIN, f"{setup_entry.entry_id}_doorbell"
    )

    event_callback(TwoNEvent(id=13, event="KeyPressed", params={"key": "%1"}))
    await hass.async_block_till_done()

    state = hass.states.get(doorbell_entity)
    assert state.attributes["event_type"] == "pressed"
    assert state.attributes["button"] == "%1"


async def test_call_session_updates_sensors(
    hass: HomeAssistant, setup_entry: MockConfigEntry, patch_api: MagicMock
) -> None:
    """A ringing call updates the call state sensor and ringing sensor."""
    event_callback = patch_api.register_event_callback.call_args[0][0]
    registry = er.async_get(hass)
    prefix = setup_entry.entry_id

    event_callback(
        TwoNEvent(
            id=14,
            event="CallStateChanged",
            params={
                "direction": "incoming",
                "state": "ringing",
                "peer": "sip:100@10.0.0.1",
                "session": 1,
                "call": 1,
            },
        )
    )
    await hass.async_block_till_done()

    call_state_entity = registry.async_get_entity_id(
        "sensor", DOMAIN, f"{prefix}_call_state"
    )
    assert hass.states.get(call_state_entity).state == "ringing"
    ringing_entity = registry.async_get_entity_id(
        "binary_sensor", DOMAIN, f"{prefix}_ringing"
    )
    assert hass.states.get(ringing_entity).state == "on"

    event_callback(
        TwoNEvent(
            id=15,
            event="CallStateChanged",
            params={"direction": "incoming", "state": "terminated", "session": 1},
        )
    )
    await hass.async_block_till_done()
    assert hass.states.get(call_state_entity).state == "idle"
    assert hass.states.get(ringing_entity).state == "off"


async def test_lock_unlock_calls_api(
    hass: HomeAssistant, setup_entry: MockConfigEntry, patch_api: MagicMock
) -> None:
    """Unlocking the lock activates the switch."""
    registry = er.async_get(hass)
    lock_entity = registry.async_get_entity_id(
        "lock", DOMAIN, f"{setup_entry.entry_id}_lock_1"
    )
    await hass.services.async_call(
        "lock", "unlock", {"entity_id": lock_entity}, blocking=True
    )
    patch_api.set_switch.assert_any_call(1, "on")


async def test_dial_service(
    hass: HomeAssistant, setup_entry: MockConfigEntry, patch_api: MagicMock
) -> None:
    """The dial service resolves the device and calls the API."""
    from homeassistant.helpers import device_registry as dr

    device = dr.async_get(hass).async_get_device(
        identifiers={(DOMAIN, setup_entry.entry_id)}
    )
    await hass.services.async_call(
        DOMAIN,
        "dial",
        {"device_id": device.id, "number": "sip:100@10.0.0.1"},
        blocking=True,
    )
    patch_api.dial.assert_called_once_with("sip:100@10.0.0.1")


async def test_answer_service_defaults_to_ringing_session(
    hass: HomeAssistant, setup_entry: MockConfigEntry, patch_api: MagicMock
) -> None:
    """The answer service picks the ringing incoming session by default."""
    from homeassistant.helpers import device_registry as dr

    coordinator = setup_entry.runtime_data
    coordinator.data.sessions[1] = make_call_session("ringing")

    device = dr.async_get(hass).async_get_device(
        identifiers={(DOMAIN, setup_entry.entry_id)}
    )
    await hass.services.async_call(
        DOMAIN, "answer", {"device_id": device.id}, blocking=True
    )
    patch_api.answer_call.assert_called_once_with(1)


async def test_switch_command_coerces_string_values(
    hass: HomeAssistant, setup_entry: MockConfigEntry, patch_api: MagicMock
) -> None:
    """Templated string values are coerced like other services do."""
    from homeassistant.helpers import device_registry as dr

    device = dr.async_get(hass).async_get_device(
        identifiers={(DOMAIN, setup_entry.entry_id)}
    )
    await hass.services.async_call(
        DOMAIN,
        "switch_command",
        {"device_id": device.id, "switch": "1", "action": "trigger"},
        blocking=True,
    )
    patch_api.set_switch.assert_called_once_with(1, "trigger", None)


async def test_privilege_error_does_not_trigger_reauth(
    hass: HomeAssistant, setup_entry: MockConfigEntry, patch_api: MagicMock
) -> None:
    """Narrowed privileges degrade the update instead of prompting re-auth."""
    from custom_components.two_n_intercom.hapi.exceptions import TwoNPrivilegeError

    coordinator = setup_entry.runtime_data
    patch_api.get_switch_status.side_effect = TwoNPrivilegeError("no privilege")

    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert coordinator.last_update_success is False
    assert not [
        flow
        for flow in hass.config_entries.flow.async_progress()
        if flow["context"].get("source") == "reauth"
    ]
