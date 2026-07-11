"""DataUpdateCoordinator for the 2N Intercom integration."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_USERNAME,
    EVENT_HOMEASSISTANT_STOP,
)
from homeassistant.core import callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.httpx_client import get_async_client
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    ATTR_DEVICE_NAME,
    ATTR_EVENT,
    ATTR_PARAMS,
    CONF_SCAN_INTERVAL,
    CONF_VERIFY_SSL,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_VERIFY_SSL,
    DOMAIN,
    EVENT_TWO_N_EVENT,
    LOGGER,
)
from .data import TwoNData
from .hapi.api import TwoNApiClient
from .hapi.exceptions import (
    TwoNAuthError,
    TwoNError,
    TwoNNotSupportedError,
    TwoNPrivilegeError,
)
from .hapi.models import CallSession, IoPortStatus, SwitchStatus

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .data import TwoNConfigEntry
    from .hapi.models import CameraCaps, IoPort, SwitchCaps, SystemInfo, TwoNEvent


def signal_event(entry_id: str) -> str:
    """Dispatcher signal name for device events of a config entry."""
    return f"{DOMAIN}_{entry_id}_event"


class TwoNUpdateCoordinator(DataUpdateCoordinator[TwoNData]):
    """Poll device state and push real-time events from the log API."""

    config_entry: TwoNConfigEntry

    def __init__(self, hass: HomeAssistant, entry: TwoNConfigEntry) -> None:
        """Initialize the coordinator and its API client."""
        scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass=hass,
            logger=LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
            always_update=False,
        )
        self.config_entry = entry
        verify_ssl = entry.data.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL)
        self.api = TwoNApiClient(
            host=entry.data[CONF_HOST],
            username=entry.data[CONF_USERNAME],
            password=entry.data[CONF_PASSWORD],
            client=get_async_client(hass, verify_ssl=verify_ssl),
        )

        # Capabilities discovered during setup.
        self.system_info: SystemInfo | None = None
        self.system_caps: dict[str, str] = {}
        self.switch_caps: list[SwitchCaps] = []
        self.io_caps: list[IoPort] = []
        self.camera_caps: CameraCaps | None = None
        self.supported_events: list[str] = []
        self.has_switches = False
        self.has_io = False
        self.has_camera = False
        self.has_calls = False
        self.has_phone = False
        self.has_system_status = False

        # Last received event per event type, for event-driven entities.
        self.event_states: dict[str, TwoNEvent] = {}

        self._listener_started = False
        self._shutdown_remove_listener = None

    # ----------------------------------------------------------- Lifecycle --

    async def _async_setup(self) -> None:
        """Discover device identity and capabilities once, before first poll."""
        self._shutdown_remove_listener = self.hass.bus.async_listen_once(
            EVENT_HOMEASSISTANT_STOP, self._async_shutdown
        )

        try:
            self.system_info = await self.api.get_system_info()
        except TwoNPrivilegeError as err:
            msg = f"Unable to fetch device info: {err}"
            raise UpdateFailed(msg) from err
        except TwoNAuthError as err:
            raise ConfigEntryAuthFailed(err) from err
        except TwoNError as err:
            msg = f"Unable to fetch device info: {err}"
            raise UpdateFailed(msg) from err

        self.system_caps = (
            await self._probe(self.api.get_system_caps, "system caps") or {}
        )

        self.switch_caps = await self._probe(self.api.get_switch_caps, "switch") or []
        self.has_switches = bool(self.switch_caps)

        self.io_caps = await self._probe(self.api.get_io_caps, "io") or []
        self.has_io = bool(self.io_caps)

        self.camera_caps = await self._probe(self.api.get_camera_caps, "camera")
        self.has_camera = bool(self.camera_caps and self.camera_caps.jpeg_resolutions)

        self.supported_events = (
            await self._probe(self.api.get_log_caps, "logging") or []
        )

        self.has_calls = await self._probe(self.api.get_call_status, "call") is not None
        self.has_phone = (
            await self._probe(self.api.get_phone_status, "phone") is not None
        )
        self.has_system_status = (
            await self._probe(self.api.get_system_status, "system status") is not None
        )

        LOGGER.debug(
            "Capabilities of %s: switches=%s io=%s camera=%s calls=%s phone=%s "
            "events=%s",
            self.api.host,
            [caps.switch for caps in self.switch_caps],
            [port.port for port in self.io_caps],
            self.has_camera,
            self.has_calls,
            self.has_phone,
            self.supported_events,
        )

    async def _probe(self, method: Any, name: str) -> Any:
        """Call a caps/status endpoint, returning None if unsupported."""
        try:
            return await method()
        except (TwoNNotSupportedError, TwoNPrivilegeError) as err:
            LOGGER.debug("%s API not available on %s: %s", name, self.api.host, err)
            return None
        except TwoNAuthError as err:
            raise ConfigEntryAuthFailed(err) from err
        except TwoNError as err:
            LOGGER.warning("Error probing %s API on %s: %s", name, self.api.host, err)
            return None

    async def _async_shutdown(self, _event: Any) -> None:
        """Handle Home Assistant shutdown."""
        self._shutdown_remove_listener = None
        await self.async_unload()

    async def async_unload(self) -> None:
        """Stop the event listener and release resources."""
        if self._shutdown_remove_listener:
            self._shutdown_remove_listener()
            self._shutdown_remove_listener = None
        await self.api.close()
        self._listener_started = False

    # ------------------------------------------------------------- Polling --

    async def _async_update_data(self) -> TwoNData:
        """Fetch the current state of all supported subsystems."""
        data = TwoNData()
        try:
            if self.has_system_status:
                data.system_status = await self.api.get_system_status()
            if self.has_switches:
                data.switches = {
                    status.switch: status
                    for status in await self.api.get_switch_status()
                }
            if self.has_io:
                data.ports = {
                    status.port: status for status in await self.api.get_io_status()
                }
            if self.has_calls:
                data.sessions = {
                    session.session: session
                    for session in await self.api.get_call_status()
                }
            if self.has_phone:
                data.accounts = {
                    account.account: account
                    for account in await self.api.get_phone_status()
                }
        except TwoNPrivilegeError as err:
            # Privileges were narrowed on the device after setup. The
            # credentials are still valid, so a re-auth prompt would be
            # wrong; surface as a normal update failure instead.
            raise UpdateFailed(err) from err
        except TwoNAuthError as err:
            raise ConfigEntryAuthFailed(err) from err
        except TwoNError as err:
            raise UpdateFailed(err) from err

        if not self._listener_started and self.supported_events:
            self.api.register_event_callback(self._handle_event)
            self.api.register_auth_error_callback(self._trigger_reauth)
            self.api.start_event_listener()
            self._listener_started = True

        return data

    # -------------------------------------------------------------- Events --

    @callback
    def _trigger_reauth(self) -> None:
        """Start re-auth when the background event loop hits an auth error."""
        LOGGER.warning(
            "2N authentication failed for %s; starting re-auth flow",
            self.config_entry.title,
        )
        self.config_entry.async_start_reauth(self.hass)

    @callback
    def _handle_event(self, event: TwoNEvent) -> None:
        """Process one device event: update state, notify entities, fire bus."""
        self.event_states[event.event] = event

        data_changed = self._apply_event_to_data(event)

        # Fire a bus event so users can build automations on raw device events.
        device_registry = dr.async_get(self.hass)
        device = device_registry.async_get_device(
            identifiers={(DOMAIN, self.config_entry.entry_id)}
        )
        self.hass.bus.async_fire(
            EVENT_TWO_N_EVENT,
            {
                "device_id": device.id if device else None,
                ATTR_DEVICE_NAME: self.config_entry.title,
                ATTR_EVENT: event.event,
                ATTR_PARAMS: event.params,
            },
        )

        # Notify event-driven entities (event platform, binary sensors).
        async_dispatcher_send(
            self.hass, signal_event(self.config_entry.entry_id), event
        )

        if data_changed and self.data is not None:
            self.async_set_updated_data(self.data)
        else:
            # Event-only state (e.g. motion) still needs listeners refreshed.
            self.async_update_listeners()

    def _apply_event_to_data(self, event: TwoNEvent) -> bool:
        """Fold state-bearing events into the polled data model."""
        if self.data is None:
            return False
        params = event.params
        if event.event == "SwitchStateChanged" and "switch" in params:
            switch_id = params["switch"]
            current = self.data.switches.get(switch_id)
            state = bool(params.get("state"))
            if current is not None:
                self.data.switches[switch_id] = replace(current, active=state)
            else:
                self.data.switches[switch_id] = SwitchStatus(
                    switch=switch_id, active=state
                )
            return True
        if event.event in ("InputChanged", "OutputChanged") and "port" in params:
            port_id = params["port"]
            state = int(bool(params.get("state")))
            self.data.ports[port_id] = IoPortStatus(port=port_id, state=state)
            return True
        if event.event == "CallStateChanged":
            session_id = params.get("session")
            if session_id is None:
                return False
            state = params.get("state")
            if state == "terminated":
                self.data.sessions.pop(session_id, None)
            else:
                self.data.sessions[session_id] = CallSession(
                    session=session_id,
                    direction=params.get("direction"),
                    state=state,
                )
            return True
        return False
