"""Button platform for the 2N Intercom integration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.button import (
    ButtonDeviceClass,
    ButtonEntity,
)
from homeassistant.const import EntityCategory

from .entity import TwoNEntity

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import TwoNUpdateCoordinator
    from .data import TwoNConfigEntry
    from .hapi.models import SwitchCaps


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001
    entry: TwoNConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the button platform."""
    coordinator = entry.runtime_data

    entities: list[ButtonEntity] = [TwoNRestartButton(coordinator)]
    entities.extend(
        TwoNSwitchTriggerButton(coordinator, caps)
        for caps in coordinator.switch_caps
        if caps.enabled
    )
    async_add_entities(entities)


class TwoNRestartButton(TwoNEntity, ButtonEntity):
    """Button that restarts the intercom."""

    _attr_device_class = ButtonDeviceClass.RESTART
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: TwoNUpdateCoordinator) -> None:
        """Initialize the restart button."""
        super().__init__(coordinator, "restart")

    async def async_press(self) -> None:
        """Restart the device."""
        await self.coordinator.api.restart()


class TwoNSwitchTriggerButton(TwoNEntity, ButtonEntity):
    """Button that pulses a switch for its configured hold time."""

    _attr_translation_key = "switch_trigger"

    def __init__(self, coordinator: TwoNUpdateCoordinator, caps: SwitchCaps) -> None:
        """Initialize for one switch number."""
        super().__init__(coordinator, f"switch_trigger_{caps.switch}")
        self._caps = caps
        self._attr_translation_placeholders = {"number": str(caps.switch)}

    async def async_press(self) -> None:
        """Trigger the switch."""
        await self.coordinator.api.set_switch(self._caps.switch, "trigger")
        await self.coordinator.async_request_refresh()
