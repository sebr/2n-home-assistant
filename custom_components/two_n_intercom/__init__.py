"""
Custom integration to integrate 2N IP intercoms with Home Assistant.

For more details about this integration, please refer to
https://github.com/sebr/2n-home-assistant
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.const import Platform
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN
from .coordinator import TwoNUpdateCoordinator
from .entity import intercom_device_info
from .services import async_register_services

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.typing import ConfigType

    from .data import TwoNConfigEntry

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.CAMERA,
    Platform.EVENT,
    Platform.LOCK,
    Platform.SENSOR,
    Platform.SWITCH,
]


async def async_setup(hass: HomeAssistant, _config: ConfigType) -> bool:
    """Register domain services once, independent of config entries."""
    async_register_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: TwoNConfigEntry) -> bool:
    """Set up this integration using the UI."""
    coordinator = TwoNUpdateCoordinator(hass=hass, entry=entry)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator

    # Register the intercom device up front so bus events can reference it
    # even before the first entity is created.
    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        **intercom_device_info(coordinator),
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: TwoNConfigEntry) -> bool:
    """Handle removal of an entry."""
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False

    await entry.runtime_data.async_unload()
    return True


async def async_reload_entry(hass: HomeAssistant, entry: TwoNConfigEntry) -> None:
    """Reload config entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)
