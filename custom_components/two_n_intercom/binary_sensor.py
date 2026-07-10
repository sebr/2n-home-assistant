"""Binary sensor platform for the 2N Intercom integration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory

from .entity import TwoNEntity

if TYPE_CHECKING:
    from collections.abc import Callable

    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import TwoNUpdateCoordinator
    from .data import TwoNConfigEntry, TwoNData
    from .hapi.models import IoPort, PhoneAccount


@dataclass(frozen=True, kw_only=True)
class TwoNEventBinarySensorDescription(BinarySensorEntityDescription):
    """A binary sensor fed by a device event with in/out semantics."""

    event_type: str
    # Param values meaning "on"; 2N uses "in"/"out" for most, door uses
    # "opened"/"closed".
    on_states: tuple[str, ...] = ("in",)


EVENT_SENSORS: tuple[TwoNEventBinarySensorDescription, ...] = (
    TwoNEventBinarySensorDescription(
        key="motion",
        event_type="MotionDetected",
        device_class=BinarySensorDeviceClass.MOTION,
        translation_key="motion",
    ),
    TwoNEventBinarySensorDescription(
        key="noise",
        event_type="NoiseDetected",
        device_class=BinarySensorDeviceClass.SOUND,
        translation_key="noise",
    ),
    TwoNEventBinarySensorDescription(
        key="tamper",
        event_type="TamperSwitchActivated",
        device_class=BinarySensorDeviceClass.TAMPER,
        entity_category=EntityCategory.DIAGNOSTIC,
        translation_key="tamper",
    ),
    TwoNEventBinarySensorDescription(
        key="door",
        event_type="DoorStateChanged",
        device_class=BinarySensorDeviceClass.DOOR,
        on_states=("opened",),
        translation_key="door",
    ),
    TwoNEventBinarySensorDescription(
        key="unauthorized_door_open",
        event_type="UnauthorizedDoorOpen",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        translation_key="unauthorized_door_open",
    ),
    TwoNEventBinarySensorDescription(
        key="door_open_too_long",
        event_type="DoorOpenTooLong",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        translation_key="door_open_too_long",
    ),
    TwoNEventBinarySensorDescription(
        key="switches_blocked",
        event_type="SwitchesBlocked",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        translation_key="switches_blocked",
    ),
)


@dataclass(frozen=True, kw_only=True)
class TwoNCallBinarySensorDescription(BinarySensorEntityDescription):
    """A binary sensor derived from the call session list."""

    value_fn: Callable[[TwoNData], bool]


CALL_SENSORS: tuple[TwoNCallBinarySensorDescription, ...] = (
    TwoNCallBinarySensorDescription(
        key="call_in_progress",
        translation_key="call_in_progress",
        device_class=BinarySensorDeviceClass.RUNNING,
        value_fn=lambda data: any(
            session.state == "connected" for session in data.sessions.values()
        ),
    ),
    TwoNCallBinarySensorDescription(
        key="ringing",
        translation_key="ringing",
        device_class=BinarySensorDeviceClass.SOUND,
        value_fn=lambda data: any(
            session.state == "ringing" for session in data.sessions.values()
        ),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001
    entry: TwoNConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the binary sensor platform."""
    coordinator = entry.runtime_data

    entities: list[BinarySensorEntity] = [
        TwoNEventBinarySensor(coordinator, description)
        for description in EVENT_SENSORS
        if description.event_type in coordinator.supported_events
    ]
    if coordinator.has_calls:
        entities.extend(
            TwoNCallBinarySensor(coordinator, description)
            for description in CALL_SENSORS
        )
    entities.extend(
        TwoNInputPortBinarySensor(coordinator, port)
        for port in coordinator.io_caps
        if port.type == "input"
    )
    if coordinator.has_phone:
        entities.extend(
            TwoNSipRegisteredBinarySensor(coordinator, account)
            for account in (coordinator.data.accounts or {}).values()
            if account.enabled
        )
    async_add_entities(entities)


class TwoNEventBinarySensor(TwoNEntity, BinarySensorEntity):
    """Binary sensor reflecting the last in/out event of one type."""

    entity_description: TwoNEventBinarySensorDescription

    def __init__(
        self,
        coordinator: TwoNUpdateCoordinator,
        description: TwoNEventBinarySensorDescription,
    ) -> None:
        """Initialize from an event sensor description."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        """Return the state derived from the last event, if any."""
        event = self.coordinator.event_states.get(self.entity_description.event_type)
        if event is None:
            return None
        return event.params.get("state") in self.entity_description.on_states


class TwoNCallBinarySensor(TwoNEntity, BinarySensorEntity):
    """Binary sensor derived from active call sessions."""

    entity_description: TwoNCallBinarySensorDescription

    def __init__(
        self,
        coordinator: TwoNUpdateCoordinator,
        description: TwoNCallBinarySensorDescription,
    ) -> None:
        """Initialize from a call sensor description."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool:
        """Return the state computed from the session list."""
        return self.entity_description.value_fn(self.coordinator.data)


class TwoNInputPortBinarySensor(TwoNEntity, BinarySensorEntity):
    """A logic input port exposed by the IO API."""

    _attr_translation_key = "io_input"

    def __init__(self, coordinator: TwoNUpdateCoordinator, port: IoPort) -> None:
        """Initialize for one input port."""
        super().__init__(coordinator, f"io_{port.port}")
        self._port = port
        self._attr_translation_placeholders = {"port": port.port}

    @property
    def available(self) -> bool:
        """Return True when the port is present in the polled data."""
        return super().available and self._port.port in self.coordinator.data.ports

    @property
    def is_on(self) -> bool | None:
        """Return the state of the input port."""
        status = self.coordinator.data.ports.get(self._port.port)
        return bool(status.state) if status else None


class TwoNSipRegisteredBinarySensor(TwoNEntity, BinarySensorEntity):
    """SIP registration state of one account."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "sip_registered"

    def __init__(
        self, coordinator: TwoNUpdateCoordinator, account: PhoneAccount
    ) -> None:
        """Initialize for one SIP account."""
        super().__init__(coordinator, f"sip_{account.account}")
        self._account_id = account.account
        self._attr_translation_placeholders = {"number": str(account.account)}

    @property
    def is_on(self) -> bool | None:
        """Return True when the account is registered."""
        account = self.coordinator.data.accounts.get(self._account_id)
        return account.registered if account else None

    @property
    def extra_state_attributes(self) -> dict[str, str | None]:
        """Expose the SIP number."""
        account = self.coordinator.data.accounts.get(self._account_id)
        return {"sip_number": account.sip_number if account else None}
