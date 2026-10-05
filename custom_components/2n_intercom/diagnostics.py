"""Diagnostics support for the 2N Intercom integration."""

from __future__ import annotations

from dataclasses import asdict
from typing import TYPE_CHECKING, Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .data import TwoNConfigEntry

TO_REDACT = {CONF_PASSWORD, CONF_USERNAME, "serialNumber", "macAddr"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,  # noqa: ARG001
    entry: TwoNConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    data = coordinator.data

    return {
        "entry_data": async_redact_data(dict(entry.data), TO_REDACT),
        "options": dict(entry.options),
        "system_info": async_redact_data(
            coordinator.system_info.raw if coordinator.system_info else {}, TO_REDACT
        ),
        "system_caps": coordinator.system_caps,
        "switch_caps": [asdict(caps) for caps in coordinator.switch_caps],
        "io_caps": [asdict(port) for port in coordinator.io_caps],
        "camera_caps": asdict(coordinator.camera_caps)
        if coordinator.camera_caps
        else None,
        "supported_events": coordinator.supported_events,
        "capabilities": {
            "switches": coordinator.has_switches,
            "io": coordinator.has_io,
            "camera": coordinator.has_camera,
            "calls": coordinator.has_calls,
            "phone": coordinator.has_phone,
            "system_status": coordinator.has_system_status,
        },
        "data": {
            "system_status": asdict(data.system_status) if data.system_status else None,
            "switches": {key: asdict(value) for key, value in data.switches.items()},
            "ports": {key: asdict(value) for key, value in data.ports.items()},
            "sessions": {key: asdict(value) for key, value in data.sessions.items()},
            "accounts": {
                key: async_redact_data(asdict(value), {"sip_number"})
                for key, value in data.accounts.items()
            },
        },
        "last_events": {
            event_type: {
                "id": event.id,
                "utc_time": event.utc_time,
                "params": async_redact_data(event.params, {"code", "uid", "uuid"}),
            }
            for event_type, event in coordinator.event_states.items()
        },
    }
