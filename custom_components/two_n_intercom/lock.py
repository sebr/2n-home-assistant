"""
Lock platform for the 2N Intercom integration.

Each 2N switch usually drives a door strike, so switches are also exposed
as lock entities. Which switches appear as locks is configurable in the
integration options (all enabled switches by default).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.lock import LockEntity, LockEntityFeature

from .const import CONF_LOCK_SWITCHES
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
    """Set up the lock platform."""
    coordinator = entry.runtime_data

    selected = entry.options.get(CONF_LOCK_SWITCHES)
    async_add_entities(
        TwoNDoorLock(coordinator, caps)
        for caps in coordinator.switch_caps
        if caps.enabled and (selected is None or str(caps.switch) in selected)
    )


class TwoNDoorLock(TwoNEntity, LockEntity):
    """
    A door lock backed by a 2N switch.

    The lock is "unlocked" while the switch is active. Monostable switches
    return to locked automatically after their configured hold time.
    """

    _attr_supported_features = LockEntityFeature.OPEN
    _attr_translation_key = "door"

    def __init__(self, coordinator: TwoNUpdateCoordinator, caps: SwitchCaps) -> None:
        """Initialize for one switch number."""
        super().__init__(coordinator, f"lock_{caps.switch}")
        self._caps = caps
        self._attr_translation_placeholders = {"number": str(caps.switch)}

    @property
    def available(self) -> bool:
        """Return True when the switch is present in the polled data."""
        return super().available and self._caps.switch in self.coordinator.data.switches

    @property
    def is_locked(self) -> bool | None:
        """Return True while the switch is inactive."""
        status = self.coordinator.data.switches.get(self._caps.switch)
        return not status.active if status else None

    async def async_unlock(self, **_kwargs: Any) -> None:
        """Activate the switch to release the door."""
        await self.coordinator.api.set_switch(self._caps.switch, "on")
        await self.coordinator.async_request_refresh()

    async def async_lock(self, **_kwargs: Any) -> None:
        """Deactivate the switch."""
        await self.coordinator.api.set_switch(self._caps.switch, "off")
        await self.coordinator.async_request_refresh()

    async def async_open(self, **_kwargs: Any) -> None:
        """Pulse the switch to briefly open the door."""
        await self.coordinator.api.set_switch(self._caps.switch, "trigger")
        await self.coordinator.async_request_refresh()
