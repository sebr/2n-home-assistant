"""Sensor platform for the 2N Intercom integration."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.util import dt as dt_util

from .entity import TwoNEntity

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import TwoNUpdateCoordinator
    from .data import TwoNConfigEntry

# Call states ordered by display precedence when multiple sessions exist.
CALL_STATE_PRECEDENCE = ("connected", "ringing", "connecting")

# Suppress uptime jitter smaller than this.
BOOT_TIME_TOLERANCE = timedelta(seconds=30)


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001
    entry: TwoNConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform."""
    coordinator = entry.runtime_data

    entities: list[SensorEntity] = []
    if coordinator.has_system_status:
        entities.append(TwoNBootTimeSensor(coordinator))
    if coordinator.has_calls:
        entities.append(TwoNCallStateSensor(coordinator))
    if "CardEntered" in coordinator.supported_events:
        entities.append(TwoNLastCardSensor(coordinator))
    if "UserAuthenticated" in coordinator.supported_events:
        entities.append(TwoNLastUserSensor(coordinator))
    if "KeyPressed" in coordinator.supported_events:
        entities.append(TwoNLastKeySensor(coordinator))
    async_add_entities(entities)


class TwoNBootTimeSensor(TwoNEntity, SensorEntity):
    """Timestamp of the last device restart, derived from upTime."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "last_restart"

    def __init__(self, coordinator: TwoNUpdateCoordinator) -> None:
        """Initialize the boot time sensor."""
        super().__init__(coordinator, "last_restart")
        self._boot_time: datetime | None = None

    @property
    def native_value(self) -> datetime | None:
        """Return the boot timestamp, tolerant of polling jitter."""
        status = self.coordinator.data.system_status
        if status is None or status.up_time is None:
            return self._boot_time
        boot_time = dt_util.utcnow() - timedelta(seconds=status.up_time)
        if (
            self._boot_time is None
            or abs(boot_time - self._boot_time) > BOOT_TIME_TOLERANCE
        ):
            self._boot_time = boot_time
        return self._boot_time


class TwoNCallStateSensor(TwoNEntity, SensorEntity):
    """Overall call state of the intercom."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["idle", "connecting", "ringing", "connected"]  # noqa: RUF012
    _attr_translation_key = "call_state"

    def __init__(self, coordinator: TwoNUpdateCoordinator) -> None:
        """Initialize the call state sensor."""
        super().__init__(coordinator, "call_state")

    @property
    def native_value(self) -> str:
        """Return the most significant state across active sessions."""
        states = {session.state for session in self.coordinator.data.sessions.values()}
        for state in CALL_STATE_PRECEDENCE:
            if state in states:
                return state
        return "idle"

    @property
    def extra_state_attributes(self) -> dict[str, list[dict[str, str | int | None]]]:
        """Expose the active sessions."""
        return {
            "sessions": [
                {
                    "session": session.session,
                    "direction": session.direction,
                    "state": session.state,
                    "peer": session.peer,
                }
                for session in self.coordinator.data.sessions.values()
            ]
        }


class TwoNLastEventSensor(TwoNEntity, SensorEntity):
    """Base for diagnostic sensors that show the last event of one type."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    # Card UIDs, user names and keypresses are privacy-sensitive and would be
    # persisted to state history. Off by default; users opt in per sensor.
    _attr_entity_registry_enabled_default = False
    event_type: str
    value_param: str

    def __init__(self, coordinator: TwoNUpdateCoordinator, key: str) -> None:
        """Initialize with the entity key."""
        super().__init__(coordinator, key)

    @property
    def native_value(self) -> str | None:
        """Return the value parameter of the last event."""
        event = self.coordinator.event_states.get(self.event_type)
        if event is None:
            return None
        return event.params.get(self.value_param)

    @property
    def extra_state_attributes(self) -> dict[str, object] | None:
        """Expose all event parameters and its timestamp."""
        event = self.coordinator.event_states.get(self.event_type)
        if event is None:
            return None
        return {**event.params, "utc_time": event.utc_time}


class TwoNLastCardSensor(TwoNLastEventSensor):
    """UID of the last RFID card presented."""

    _attr_translation_key = "last_card"
    event_type = "CardEntered"
    value_param = "uid"

    def __init__(self, coordinator: TwoNUpdateCoordinator) -> None:
        """Initialize the last card sensor."""
        super().__init__(coordinator, "last_card")


class TwoNLastUserSensor(TwoNLastEventSensor):
    """Name of the last successfully authenticated user."""

    _attr_translation_key = "last_user"
    event_type = "UserAuthenticated"
    value_param = "name"

    def __init__(self, coordinator: TwoNUpdateCoordinator) -> None:
        """Initialize the last user sensor."""
        super().__init__(coordinator, "last_user")


class TwoNLastKeySensor(TwoNLastEventSensor):
    """Last key pressed on the keypad or quick dial buttons."""

    _attr_translation_key = "last_key"
    event_type = "KeyPressed"
    value_param = "key"

    def __init__(self, coordinator: TwoNUpdateCoordinator) -> None:
        """Initialize the last key sensor."""
        super().__init__(coordinator, "last_key")
