"""Base classes for 2N Intercom entities."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER

if TYPE_CHECKING:
    from .coordinator import TwoNUpdateCoordinator


def intercom_device_info(coordinator: TwoNUpdateCoordinator) -> DeviceInfo:
    """Build the DeviceInfo for the intercom."""
    entry = coordinator.config_entry
    info = coordinator.system_info
    device_info = DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=(info.device_name if info else None) or entry.title,
        manufacturer=MANUFACTURER,
        model=info.variant if info else None,
        serial_number=info.serial_number if info else None,
        sw_version=info.sw_version if info else None,
        hw_version=info.hw_version if info else None,
        configuration_url=coordinator.api.host,
    )
    if info and info.mac_addr:
        device_info["connections"] = {(CONNECTION_NETWORK_MAC, info.mac_addr)}
    return device_info


class TwoNEntity(CoordinatorEntity["TwoNUpdateCoordinator"]):
    """Base entity for all 2N Intercom entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: TwoNUpdateCoordinator, key: str) -> None:
        """Initialize with a unique id derived from the config entry and key."""
        super().__init__(coordinator=coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{key}"
        self._attr_device_info = intercom_device_info(coordinator)
