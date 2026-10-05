"""Custom types for the 2N Intercom integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

    from .coordinator import TwoNUpdateCoordinator
    from .hapi.models import (
        CallSession,
        IoPortStatus,
        PhoneAccount,
        SwitchStatus,
        SystemStatus,
    )


type TwoNConfigEntry = ConfigEntry[TwoNUpdateCoordinator]


@dataclass
class TwoNData:
    """Aggregated device state fetched by the coordinator."""

    system_status: SystemStatus | None = None
    switches: dict[int, SwitchStatus] = field(default_factory=dict)
    ports: dict[str, IoPortStatus] = field(default_factory=dict)
    sessions: dict[int, CallSession] = field(default_factory=dict)
    accounts: dict[int, PhoneAccount] = field(default_factory=dict)
