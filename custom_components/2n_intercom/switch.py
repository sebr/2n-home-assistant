"""Switch platform for the 2N Intercom integration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity

from .entity import TwoNEntity

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import TwoNUpdateCoordinator
    from .data import TwoNConfigEntry
    from .hapi.models import IoPort, SwitchCaps


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001
    entry: TwoNConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the switch platform."""
    coordinator = entry.runtime_data

    entities: list[SwitchEntity] = [
        TwoNSwitch(coordinator, caps)
        for caps in coordinator.switch_caps
        if caps.enabled
    ]
    entities.extend(
        TwoNIoOutputSwitch(coordinator, port)
        for port in coordinator.io_caps
        if port.type == "output"
    )
    async_add_entities(entities)


class TwoNSwitch(TwoNEntity, SwitchEntity):
    """A configured 2N switch (typically a door strike relay)."""

    _attr_device_class = SwitchDeviceClass.SWITCH

    def __init__(self, coordinator: TwoNUpdateCoordinator, caps: SwitchCaps) -> None:
        """Initialize for one switch number."""
        super().__init__(coordinator, f"switch_{caps.switch}")
        self._caps = caps
        self._attr_translation_key = "switch"
        self._attr_translation_placeholders = {"number": str(caps.switch)}

    @property
    def available(self) -> bool:
        """Return True when the switch is present in the polled data."""
        return super().available and self._caps.switch in self.coordinator.data.switches

    @property
    def is_on(self) -> bool | None:
        """Return the active state of the switch."""
        status = self.coordinator.data.switches.get(self._caps.switch)
        return status.active if status else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose switch configuration and lock/hold state."""
        attributes: dict[str, Any] = {
            "mode": self._caps.mode,
            "switch_on_duration": self._caps.switch_on_duration,
        }
        status = self.coordinator.data.switches.get(self._caps.switch)
        if status is not None:
            attributes["locked"] = status.locked
            attributes["held"] = status.held
        return attributes

    async def async_turn_on(self, **_kwargs: Any) -> None:
        """Activate the switch."""
        await self.coordinator.api.set_switch(self._caps.switch, "on")
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **_kwargs: Any) -> None:
        """Deactivate the switch."""
        await self.coordinator.api.set_switch(self._caps.switch, "off")
        await self.coordinator.async_request_refresh()


class TwoNIoOutputSwitch(TwoNEntity, SwitchEntity):
    """A logic output port (relay) exposed by the IO API."""

    _attr_device_class = SwitchDeviceClass.SWITCH
    # Generic logic relay; advanced use only. Opt in when wired.
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: TwoNUpdateCoordinator, port: IoPort) -> None:
        """Initialize for one output port."""
        super().__init__(coordinator, f"io_{port.port}")
        self._port = port
        self._attr_translation_key = "io_output"
        self._attr_translation_placeholders = {"port": port.port}

    @property
    def available(self) -> bool:
        """Return True when the port is present in the polled data."""
        return super().available and self._port.port in self.coordinator.data.ports

    @property
    def is_on(self) -> bool | None:
        """Return the state of the output port."""
        status = self.coordinator.data.ports.get(self._port.port)
        return bool(status.state) if status else None

    async def async_turn_on(self, **_kwargs: Any) -> None:
        """Set the output high."""
        await self.coordinator.api.set_io(self._port.port, "on")
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **_kwargs: Any) -> None:
        """Set the output low."""
        await self.coordinator.api.set_io(self._port.port, "off")
        await self.coordinator.async_request_refresh()
