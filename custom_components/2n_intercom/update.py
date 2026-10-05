"""Update platform for the 2N Intercom integration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.update import (
    UpdateDeviceClass,
    UpdateEntity,
    UpdateEntityFeature,
)
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .entity import intercom_device_info

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import TwoNFirmwareCoordinator, TwoNUpdateCoordinator
    from .data import TwoNConfigEntry


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001
    entry: TwoNConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the update platform."""
    coordinator = entry.runtime_data
    if coordinator.firmware is None:
        return

    # A failed check must not block setup; the entity shows as unavailable
    # until the next check succeeds.
    await coordinator.firmware.async_refresh()
    async_add_entities([TwoNFirmwareUpdate(coordinator, coordinator.firmware)])


class TwoNFirmwareUpdate(CoordinatorEntity["TwoNFirmwareCoordinator"], UpdateEntity):
    """Shows whether 2N offers newer firmware for the intercom."""

    _attr_has_entity_name = True
    _attr_device_class = UpdateDeviceClass.FIRMWARE
    _attr_supported_features = UpdateEntityFeature.RELEASE_NOTES
    _attr_title = "2N OS"

    def __init__(
        self,
        coordinator: TwoNUpdateCoordinator,
        firmware: TwoNFirmwareCoordinator,
    ) -> None:
        """Initialize with the device coordinator and its firmware checker."""
        super().__init__(coordinator=firmware)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_firmware"
        self._attr_device_info = intercom_device_info(coordinator)

    @property
    def installed_version(self) -> str | None:
        """Return the firmware version running on the device."""
        return self.coordinator.data.installed_version

    @property
    def latest_version(self) -> str | None:
        """Return the newest firmware version 2N offers."""
        newest = self.coordinator.data.newest
        return newest.version if newest else self.installed_version

    async def async_release_notes(self) -> str | None:
        """Return the release notes of every newer version, newest first."""
        newest = self.coordinator.data.newest
        if newest is None:
            return None
        return "\n\n".join(entry.text for entry in reversed(newest.changelog))
