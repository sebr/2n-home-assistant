"""Custom services for the 2N Intercom integration."""

from __future__ import annotations

from typing import TYPE_CHECKING

import voluptuous as vol
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN
from .hapi.exceptions import TwoNError

if TYPE_CHECKING:
    from .coordinator import TwoNUpdateCoordinator

ATTR_DEVICE_ID = "device_id"
ATTR_NUMBER = "number"
ATTR_SESSION = "session"
ATTR_REASON = "reason"
ATTR_SWITCH = "switch"
ATTR_ACTION = "action"
ATTR_TIMEOUT = "timeout"
ATTR_TEXT = "text"
ATTR_TRIGGER_ID = "trigger_id"

SERVICE_DIAL = "dial"
SERVICE_ANSWER = "answer"
SERVICE_HANGUP = "hangup"
SERVICE_SWITCH_COMMAND = "switch_command"
SERVICE_AUDIO_TEST = "audio_test"
SERVICE_DISPLAY_TEXT = "display_text"
SERVICE_AUTOMATION_TRIGGER = "automation_trigger"

SWITCH_ACTIONS = ["on", "off", "trigger", "lock", "unlock", "hold", "release"]
HANGUP_REASONS = ["normal", "rejected", "busy"]

_BASE_SCHEMA = {vol.Required(ATTR_DEVICE_ID): cv.string}

DIAL_SCHEMA = vol.Schema({**_BASE_SCHEMA, vol.Required(ATTR_NUMBER): cv.string})
ANSWER_SCHEMA = vol.Schema(
    {**_BASE_SCHEMA, vol.Optional(ATTR_SESSION): cv.positive_int}
)
HANGUP_SCHEMA = vol.Schema(
    {
        **_BASE_SCHEMA,
        vol.Optional(ATTR_SESSION): cv.positive_int,
        vol.Optional(ATTR_REASON): vol.In(HANGUP_REASONS),
    }
)
SWITCH_COMMAND_SCHEMA = vol.Schema(
    {
        **_BASE_SCHEMA,
        vol.Required(ATTR_SWITCH): vol.All(int, vol.Range(min=1, max=4)),
        vol.Required(ATTR_ACTION): vol.In(SWITCH_ACTIONS),
        vol.Optional(ATTR_TIMEOUT): vol.All(int, vol.Range(min=1, max=86400)),
    }
)
AUDIO_TEST_SCHEMA = vol.Schema(_BASE_SCHEMA)
DISPLAY_TEXT_SCHEMA = vol.Schema(
    {
        **_BASE_SCHEMA,
        vol.Required(ATTR_TEXT): cv.string,
        vol.Optional(ATTR_TIMEOUT): vol.All(int, vol.Range(min=1, max=1209600)),
    }
)
AUTOMATION_TRIGGER_SCHEMA = vol.Schema(
    {**_BASE_SCHEMA, vol.Required(ATTR_TRIGGER_ID): cv.string}
)


def _get_coordinator(hass: HomeAssistant, device_id: str) -> TwoNUpdateCoordinator:
    """Resolve a device id to the coordinator of its config entry."""
    device_registry = dr.async_get(hass)
    device = device_registry.async_get(device_id)
    if device is None:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="invalid_device",
            translation_placeholders={"device_id": device_id},
        )
    for entry_id in device.config_entries:
        entry = hass.config_entries.async_get_entry(entry_id)
        if (
            entry is not None
            and entry.domain == DOMAIN
            and entry.state is ConfigEntryState.LOADED
        ):
            return entry.runtime_data
    raise ServiceValidationError(
        translation_domain=DOMAIN,
        translation_key="invalid_device",
        translation_placeholders={"device_id": device_id},
    )


async def _wrap(coro: object) -> None:
    """Await an API call, converting client errors to HomeAssistantError."""
    try:
        await coro  # type: ignore[misc]
    except TwoNError as err:
        raise HomeAssistantError(str(err)) from err


@callback
def async_register_services(hass: HomeAssistant) -> None:
    """Register the integration services (idempotent)."""
    if hass.services.has_service(DOMAIN, SERVICE_DIAL):
        return

    async def handle_dial(call: ServiceCall) -> None:
        coordinator = _get_coordinator(hass, call.data[ATTR_DEVICE_ID])
        await _wrap(coordinator.api.dial(call.data[ATTR_NUMBER]))
        await coordinator.async_request_refresh()

    async def handle_answer(call: ServiceCall) -> None:
        coordinator = _get_coordinator(hass, call.data[ATTR_DEVICE_ID])
        session = call.data.get(ATTR_SESSION)
        if session is None:
            session = next(
                (
                    item.session
                    for item in coordinator.data.sessions.values()
                    if item.direction == "incoming" and item.state == "ringing"
                ),
                None,
            )
        if session is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="no_active_call",
            )
        await _wrap(coordinator.api.answer_call(session))
        await coordinator.async_request_refresh()

    async def handle_hangup(call: ServiceCall) -> None:
        coordinator = _get_coordinator(hass, call.data[ATTR_DEVICE_ID])
        session = call.data.get(ATTR_SESSION)
        sessions = (
            [session]
            if session is not None
            else [item.session for item in coordinator.data.sessions.values()]
        )
        if not sessions:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="no_active_call",
            )
        for item in sessions:
            await _wrap(coordinator.api.hangup_call(item, call.data.get(ATTR_REASON)))
        await coordinator.async_request_refresh()

    async def handle_switch_command(call: ServiceCall) -> None:
        coordinator = _get_coordinator(hass, call.data[ATTR_DEVICE_ID])
        await _wrap(
            coordinator.api.set_switch(
                call.data[ATTR_SWITCH],
                call.data[ATTR_ACTION],
                call.data.get(ATTR_TIMEOUT),
            )
        )
        await coordinator.async_request_refresh()

    async def handle_audio_test(call: ServiceCall) -> None:
        coordinator = _get_coordinator(hass, call.data[ATTR_DEVICE_ID])
        await _wrap(coordinator.api.audio_test())

    async def handle_display_text(call: ServiceCall) -> None:
        coordinator = _get_coordinator(hass, call.data[ATTR_DEVICE_ID])
        await _wrap(
            coordinator.api.display_text(
                call.data[ATTR_TEXT],
                timeout=call.data.get(ATTR_TIMEOUT),
            )
        )

    async def handle_automation_trigger(call: ServiceCall) -> None:
        coordinator = _get_coordinator(hass, call.data[ATTR_DEVICE_ID])
        await _wrap(coordinator.api.automation_trigger(call.data[ATTR_TRIGGER_ID]))

    hass.services.async_register(DOMAIN, SERVICE_DIAL, handle_dial, DIAL_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_ANSWER, handle_answer, ANSWER_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_HANGUP, handle_hangup, HANGUP_SCHEMA)
    hass.services.async_register(
        DOMAIN, SERVICE_SWITCH_COMMAND, handle_switch_command, SWITCH_COMMAND_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_AUDIO_TEST, handle_audio_test, AUDIO_TEST_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_DISPLAY_TEXT, handle_display_text, DISPLAY_TEXT_SCHEMA
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_AUTOMATION_TRIGGER,
        handle_automation_trigger,
        AUTOMATION_TRIGGER_SCHEMA,
    )
