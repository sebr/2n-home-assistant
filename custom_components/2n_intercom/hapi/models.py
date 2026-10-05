"""Typed models for 2N HTTP API responses."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SystemInfo:
    """Response of /api/system/info."""

    variant: str | None = None
    serial_number: str | None = None
    hw_version: str | None = None
    sw_version: str | None = None
    build_type: str | None = None
    device_name: str | None = None
    mac_addr: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SystemInfo:
        """Build from the API result payload."""
        return cls(
            variant=data.get("variant"),
            serial_number=data.get("serialNumber"),
            hw_version=data.get("hwVersion"),
            sw_version=data.get("swVersion"),
            build_type=data.get("buildType"),
            device_name=data.get("deviceName"),
            mac_addr=data.get("macAddr"),
            raw=data,
        )


@dataclass(frozen=True)
class SystemStatus:
    """Response of /api/system/status."""

    system_time: int | None = None
    up_time: int | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SystemStatus:
        """Build from the API result payload."""
        return cls(
            system_time=data.get("systemTime"),
            up_time=data.get("upTime"),
        )


@dataclass(frozen=True)
class SwitchCaps:
    """One switch entry from /api/switch/caps."""

    switch: int
    enabled: bool = False
    mode: str | None = None  # "monostable" | "bistable"
    switch_on_duration: int | None = None
    type: str | None = None  # "normal" | "security"

    @property
    def is_monostable(self) -> bool:
        """Return True if the switch automatically returns to off."""
        return self.mode == "monostable"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SwitchCaps:
        """Build from the API result payload."""
        return cls(
            switch=data["switch"],
            enabled=data.get("enabled", False),
            mode=data.get("mode"),
            switch_on_duration=data.get("switchOnDuration"),
            type=data.get("type"),
        )


@dataclass(frozen=True)
class SwitchStatus:
    """One switch entry from /api/switch/status."""

    switch: int
    active: bool = False
    locked: bool | None = None
    held: bool | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SwitchStatus:
        """Build from the API result payload."""
        return cls(
            switch=data["switch"],
            active=data.get("active", False),
            locked=data.get("locked"),
            held=data.get("held"),
        )


@dataclass(frozen=True)
class IoPort:
    """One port entry from /api/io/caps."""

    port: str
    type: str  # "input" | "output"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> IoPort:
        """Build from the API result payload."""
        return cls(port=data["port"], type=data.get("type", ""))


@dataclass(frozen=True)
class IoPortStatus:
    """One port entry from /api/io/status."""

    port: str
    state: int = 0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> IoPortStatus:
        """Build from the API result payload."""
        return cls(port=data["port"], state=data.get("state", 0))


@dataclass(frozen=True)
class CameraCaps:
    """Response of /api/camera/caps."""

    jpeg_resolutions: list[tuple[int, int]] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CameraCaps:
        """Build from the API result payload."""
        return cls(
            jpeg_resolutions=[
                (res["width"], res["height"])
                for res in data.get("jpegResolution", [])
                if "width" in res and "height" in res
            ],
            sources=[
                source["source"]
                for source in data.get("sources", [])
                if "source" in source
            ],
        )


@dataclass(frozen=True)
class CallPeer:
    """One destination of a call session."""

    id: int | None = None
    peer: str | None = None
    state: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CallPeer:
        """Build from the API result payload."""
        return cls(id=data.get("id"), peer=data.get("peer"), state=data.get("state"))


@dataclass(frozen=True)
class CallSession:
    """One session entry from /api/call/status."""

    session: int
    direction: str | None = None  # "incoming" | "outgoing"
    state: str | None = None  # "connecting" | "ringing" | "connected" | "terminated"
    calls: list[CallPeer] = field(default_factory=list)

    @property
    def peer(self) -> str | None:
        """Return the first remote party SIP URI, if known."""
        return self.calls[0].peer if self.calls else None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CallSession:
        """Build from the API result payload."""
        return cls(
            session=data["session"],
            direction=data.get("direction"),
            state=data.get("state"),
            calls=[CallPeer.from_dict(item) for item in data.get("calls", [])],
        )


@dataclass(frozen=True)
class PhoneAccount:
    """One account entry from /api/phone/status."""

    account: int
    account_type: str | None = None  # "general" | "local" | "msteams"
    enabled: bool = False
    sip_number: str | None = None
    registration_enabled: bool = False
    registered: bool = False
    register_time: int | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PhoneAccount:
        """Build from the API result payload."""
        return cls(
            account=data["account"],
            account_type=data.get("accountType"),
            enabled=data.get("enabled", False),
            sip_number=data.get("sipNumber"),
            registration_enabled=data.get("registrationEnabled", False),
            registered=data.get("registered", False),
            register_time=data.get("registerTime"),
        )


@dataclass(frozen=True)
class TwoNEvent:
    """One event entry from /api/log/pull."""

    id: int
    event: str
    utc_time: int | None = None
    up_time: int | None = None
    tz_shift: int | None = None  # minutes; localTime = utcTime + tzShift * 60
    params: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TwoNEvent:
        """Build from the API result payload."""
        return cls(
            id=data.get("id", 0),
            event=data.get("event", ""),
            utc_time=data.get("utcTime"),
            up_time=data.get("upTime"),
            tz_shift=data.get("tzShift"),
            params=data.get("params", {}),
        )
