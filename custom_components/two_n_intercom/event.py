"""Event platform for the 2N Intercom integration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.event import (
    EventDeviceClass,
    EventEntity,
)
from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .coordinator import signal_event
from .entity import TwoNEntity

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import TwoNUpdateCoordinator
    from .data import TwoNConfigEntry
    from .hapi.models import TwoNEvent

KEYPAD_KEYS = [*[str(digit) for digit in range(10)], "*", "#"]

ACCESS_EVENT_TYPES = {
    "CardEntered": "card",
    "CardHeld": "card_held",
    "CodeEntered": "code",
    "FingerEntered": "fingerprint",
    "MobKeyEntered": "mobile_key",
    "UserAuthenticated": "authenticated",
    "UserRejected": "rejected",
}

CALL_STATES = ["connecting", "ringing", "connected", "terminated"]


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001
    entry: TwoNConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the event platform."""
    coordinator = entry.runtime_data
    supported = set(coordinator.supported_events)

    entities: list[EventEntity] = []
    if "KeyPressed" in supported:
        entities.append(TwoNDoorbellEvent(coordinator))
        entities.append(TwoNKeypadEvent(coordinator))
    if supported & set(ACCESS_EVENT_TYPES):
        entities.append(TwoNAccessEvent(coordinator))
    if "CallStateChanged" in supported:
        entities.append(TwoNCallEvent(coordinator))
    async_add_entities(entities)


class TwoNEventEntity(TwoNEntity, EventEntity):
    """Base event entity subscribed to the coordinator's event signal."""

    async def async_added_to_hass(self) -> None:
        """Subscribe to device events."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                signal_event(self.coordinator.config_entry.entry_id),
                self._handle_device_event,
            )
        )

    @callback
    def _handle_device_event(self, event: TwoNEvent) -> None:
        """Handle one device event; subclasses filter and trigger."""
        raise NotImplementedError


class TwoNDoorbellEvent(TwoNEventEntity):
    """Doorbell event: a quick dial button (%1-%150) was pressed."""

    _attr_device_class = EventDeviceClass.DOORBELL
    _attr_event_types = ["ring"]  # noqa: RUF012
    _attr_translation_key = "doorbell"

    def __init__(self, coordinator: TwoNUpdateCoordinator) -> None:
        """Initialize the doorbell event entity."""
        super().__init__(coordinator, "doorbell")

    @callback
    def _handle_device_event(self, event: TwoNEvent) -> None:
        key = event.params.get("key", "")
        if event.event == "KeyPressed" and key.startswith("%"):
            self._trigger_event("ring", {"button": key})
            self.async_write_ha_state()


class TwoNKeypadEvent(TwoNEventEntity):
    """Keypad event: a numeric key, * or # was pressed."""

    _attr_event_types = KEYPAD_KEYS
    _attr_translation_key = "keypad"
    # Fires on every keypad digit, so PIN codes would be recorded to the
    # logbook. Off by default; users who want keypad automations opt in.
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: TwoNUpdateCoordinator) -> None:
        """Initialize the keypad event entity."""
        super().__init__(coordinator, "keypad")

    @callback
    def _handle_device_event(self, event: TwoNEvent) -> None:
        key = event.params.get("key", "")
        if event.event == "KeyPressed" and key in KEYPAD_KEYS:
            self._trigger_event(key)
            self.async_write_ha_state()


class TwoNAccessEvent(TwoNEventEntity):
    """Access event: card, code, fingerprint, mobile key or user auth."""

    _attr_event_types = list(dict.fromkeys(ACCESS_EVENT_TYPES.values()))  # noqa: RUF012
    _attr_translation_key = "access"

    def __init__(self, coordinator: TwoNUpdateCoordinator) -> None:
        """Initialize the access event entity."""
        super().__init__(coordinator, "access")

    @callback
    def _handle_device_event(self, event: TwoNEvent) -> None:
        event_type = ACCESS_EVENT_TYPES.get(event.event)
        if event_type is not None:
            self._trigger_event(event_type, dict(event.params))
            self.async_write_ha_state()


class TwoNCallEvent(TwoNEventEntity):
    """Call state event, useful for ring/answer automations."""

    _attr_event_types = CALL_STATES
    _attr_translation_key = "call"

    def __init__(self, coordinator: TwoNUpdateCoordinator) -> None:
        """Initialize the call event entity."""
        super().__init__(coordinator, "call")

    @callback
    def _handle_device_event(self, event: TwoNEvent) -> None:
        state = event.params.get("state")
        if event.event == "CallStateChanged" and state in CALL_STATES:
            self._trigger_event(state, dict(event.params))
            self.async_write_ha_state()
