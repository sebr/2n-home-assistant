"""
Async client for the 2N HTTP API (HAPI).

See https://wiki.2n.com/hip/hapi/latest/en for the API documentation.

The device exposes a JSON envelope for every endpoint:
    {"success": true, "result": {...}}
    {"success": false, "error": {"code": 12, "param": "port", "description": "..."}}

Authentication is HTTP Basic or Digest, configurable per service on the
device. The client auto-negotiates by inspecting the WWW-Authenticate
challenge and caches the working auth scheme.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import TYPE_CHECKING, Any

import httpx

from .exceptions import (
    TwoNApiError,
    TwoNAuthError,
    TwoNConnectionError,
    TwoNError,
    TwoNNotSupportedError,
    TwoNPrivilegeError,
)
from .models import (
    CallSession,
    CameraCaps,
    IoPort,
    IoPortStatus,
    PhoneAccount,
    SwitchCaps,
    SwitchStatus,
    SystemInfo,
    SystemStatus,
    TwoNEvent,
)

if TYPE_CHECKING:
    from collections.abc import Callable

LOGGER = logging.getLogger(__name__)

API_TIMEOUT = 10.0

# Server-side long-poll duration for /api/log/pull. The HTTP timeout must
# exceed it so the device, not the client, terminates the poll.
LOG_PULL_TIMEOUT = 30
LOG_PULL_HTTP_TIMEOUT = LOG_PULL_TIMEOUT + 15

# Subscription expires after this many seconds without a pull.
LOG_SUBSCRIPTION_DURATION = 120

# Reconnect backoff bounds for the event listener loop.
RECONNECT_DELAY_MIN = 5
RECONNECT_DELAY_MAX = 60

# Error codes returned in the device's error envelope
# (https://wiki.2n.com/hip/hapi/latest/en - HTTP API responses).
ERROR_FUNCTION_NOT_SUPPORTED = 1
ERROR_INVALID_REQUEST_PATH = 2
ERROR_INVALID_REQUEST_METHOD = 3
ERROR_FUNCTION_DISABLED = 4
ERROR_INVALID_CONNECTION_TYPE = 7  # HTTPS required
ERROR_INVALID_AUTHENTICATION_METHOD = 8
ERROR_AUTHORISATION_REQUIRED = 9  # accompanies HTTP 401
ERROR_INSUFFICIENT_PRIVILEGES = 10
ERROR_MISSING_MANDATORY_PARAMETER = 11
ERROR_INVALID_PARAMETER_VALUE = 12
ERROR_PARAMETER_DATA_TOO_BIG = 13
ERROR_UNSPECIFIED_PROCESSING_ERROR = 14
ERROR_NO_DATA_AVAILABLE = 15

_NOT_SUPPORTED_CODES = {ERROR_FUNCTION_NOT_SUPPORTED, ERROR_FUNCTION_DISABLED}
_AUTH_CODES = {ERROR_AUTHORISATION_REQUIRED, ERROR_INVALID_AUTHENTICATION_METHOD}


class TwoNApiClient:
    """Async client for a single 2N intercom."""

    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        client: httpx.AsyncClient,
    ) -> None:
        """Initialize the client with a base URL, credentials and HTTP client."""
        self._base = host.rstrip("/")
        self._username = username
        self._password = password
        self._client = client
        self._auth: httpx.Auth | None = None

        self._event_task: asyncio.Task | None = None
        self._event_callbacks: list[Callable[[TwoNEvent], None]] = []
        self._auth_error_callbacks: list[Callable[[], None]] = []

    @property
    def host(self) -> str:
        """Return the base URL of the device."""
        return self._base

    # ---------------------------------------------------------------- HTTP --

    async def _request(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        method: str = "GET",
        timeout: float = API_TIMEOUT,  # noqa: ASYNC109
        json: Any = None,
    ) -> httpx.Response:
        """Perform a request, negotiating Basic vs Digest auth on first use."""
        url = f"{self._base}{path}"
        auth = self._auth or httpx.DigestAuth(self._username, self._password)
        try:
            response = await self._client.request(
                method, url, params=params, auth=auth, timeout=timeout, json=json
            )
            if response.status_code == httpx.codes.UNAUTHORIZED and self._auth is None:
                # The device may be configured for Basic authentication, in
                # which case the digest attempt never sends credentials.
                challenge = response.headers.get("www-authenticate", "")
                if challenge.lower().startswith("basic"):
                    basic = httpx.BasicAuth(self._username, self._password)
                    response = await self._client.request(
                        method,
                        url,
                        params=params,
                        auth=basic,
                        timeout=timeout,
                        json=json,
                    )
                    if response.status_code != httpx.codes.UNAUTHORIZED:
                        self._auth = basic
                else:
                    self._auth = auth
        except httpx.TimeoutException as err:
            msg = f"Timeout connecting to {self._base}"
            raise TwoNConnectionError(msg) from err
        except httpx.HTTPError as err:
            msg = f"Error connecting to {self._base}: {err}"
            raise TwoNConnectionError(msg) from err

        if response.status_code == httpx.codes.UNAUTHORIZED:
            self._auth = None
            msg = "Authentication failed; check username and password"
            raise TwoNAuthError(msg)
        if response.status_code == httpx.codes.FORBIDDEN:
            msg = f"Account lacks the privilege required for {path}"
            raise TwoNPrivilegeError(msg)

        if self._auth is None:
            self._auth = auth
        return response

    async def _api_call(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        method: str = "GET",
        timeout: float = API_TIMEOUT,  # noqa: ASYNC109
        json: Any = None,
    ) -> Any:
        """
        Perform a request and unwrap the JSON envelope.

        Returns the ``result`` object. Some firmware versions return a bare
        JSON value without the envelope (notably /api/call/status); that
        value is returned as-is.
        """
        response = await self._request(
            path, params=params, method=method, timeout=timeout, json=json
        )
        try:
            payload = response.json()
        except ValueError as err:
            msg = f"Invalid JSON from {path} (HTTP {response.status_code})"
            raise TwoNError(msg) from err

        if not isinstance(payload, dict):
            return payload

        if payload.get("success"):
            return payload.get("result") or {}

        error = payload.get("error") or {}
        code = error.get("code", 0)
        description = error.get("description", "")
        param = error.get("param")
        if code in _NOT_SUPPORTED_CODES:
            raise TwoNNotSupportedError(code, description, param)
        if code == ERROR_INSUFFICIENT_PRIVILEGES:
            msg = f"Account lacks the privilege required for {path}"
            raise TwoNPrivilegeError(msg)
        if code in _AUTH_CODES:
            msg = f"Authentication failed for {path}: {description}"
            raise TwoNAuthError(msg)
        raise TwoNApiError(code, description, param)

    # -------------------------------------------------------------- System --

    async def get_system_info(self) -> SystemInfo:
        """Return static device information (serial, versions, name)."""
        return SystemInfo.from_dict(await self._api_call("/api/system/info"))

    async def get_system_status(self) -> SystemStatus:
        """Return the current device status (time, uptime)."""
        return SystemStatus.from_dict(await self._api_call("/api/system/status"))

    async def get_system_caps(self) -> dict[str, str]:
        """
        Return the device feature flags from /api/system/caps.

        Each key (e.g. "camera", "doorSensor", "motionDetection") maps to
        "active" or "active,licensed".
        """
        result = await self._api_call("/api/system/caps")
        return result.get("options") or {}

    async def restart(self) -> None:
        """Restart the device."""
        await self._api_call("/api/system/restart")

    # -------------------------------------------------------------- Switch --

    async def get_switch_caps(self) -> list[SwitchCaps]:
        """Return the configured switches and their capabilities."""
        result = await self._api_call("/api/switch/caps")
        return [SwitchCaps.from_dict(item) for item in result.get("switches", [])]

    async def get_switch_status(self) -> list[SwitchStatus]:
        """Return the current state of all switches."""
        result = await self._api_call("/api/switch/status")
        return [SwitchStatus.from_dict(item) for item in result.get("switches", [])]

    async def set_switch(
        self,
        switch: int,
        action: str,
        timeout: int | None = None,  # noqa: ASYNC109
    ) -> None:
        """
        Control a switch.

        Action is on, off, trigger, lock, unlock, hold or release; timeout
        (seconds) auto-releases a hold.
        """
        params: dict[str, Any] = {"switch": switch, "action": action}
        if timeout is not None:
            params["timeout"] = timeout
        await self._api_call("/api/switch/ctrl", params=params)

    # ------------------------------------------------------------------ IO --

    async def get_io_caps(self) -> list[IoPort]:
        """Return the available logic input/output ports."""
        result = await self._api_call("/api/io/caps")
        return [IoPort.from_dict(item) for item in result.get("ports", [])]

    async def get_io_status(self) -> list[IoPortStatus]:
        """Return the current state of all IO ports."""
        result = await self._api_call("/api/io/status")
        return [IoPortStatus.from_dict(item) for item in result.get("ports", [])]

    async def set_io(self, port: str, action: str) -> None:
        """Control an output port: action is on or off."""
        await self._api_call("/api/io/ctrl", params={"port": port, "action": action})

    # -------------------------------------------------------------- Camera --

    async def get_camera_caps(self) -> CameraCaps:
        """Return the camera capabilities (resolutions, sources)."""
        return CameraCaps.from_dict(await self._api_call("/api/camera/caps"))

    async def get_camera_snapshot(
        self,
        width: int,
        height: int,
        source: str | None = None,
    ) -> bytes:
        """Return a JPEG snapshot from the camera."""
        params: dict[str, Any] = {"width": width, "height": height}
        if source:
            params["source"] = source
        response = await self._request("/api/camera/snapshot", params=params)
        content_type = response.headers.get("content-type", "")
        if "image" not in content_type:
            # Error responses come back as the JSON envelope.
            try:
                payload = response.json()
            except ValueError:
                payload = {}
            error = payload.get("error") or {}
            raise TwoNApiError(
                error.get("code", 0),
                error.get("description", "Snapshot unavailable"),
                error.get("param"),
            )
        return response.content

    def stream_camera(
        self,
        width: int,
        height: int,
        fps: int = 5,
        source: str | None = None,
    ) -> Any:
        """
        Open an MJPEG stream (multipart/x-mixed-replace) from the camera.

        Returns the httpx streaming context manager; the caller iterates the
        response with aiter_bytes(). Authentication must already have been
        negotiated by a prior request.
        """
        params: dict[str, Any] = {"width": width, "height": height, "fps": fps}
        if source:
            params["source"] = source
        auth = self._auth or httpx.DigestAuth(self._username, self._password)
        return self._client.stream(
            "GET",
            f"{self._base}/api/camera/snapshot",
            params=params,
            auth=auth,
            timeout=httpx.Timeout(API_TIMEOUT, read=None),
        )

    # ---------------------------------------------------------------- Call --

    async def get_call_status(self, session: int | None = None) -> list[CallSession]:
        """
        Return the state of active call sessions.

        Older firmware wraps the list as result.sessions; v2.50 returns a
        bare JSON array. Both shapes are accepted.
        """
        params = {"session": session} if session is not None else None
        result = await self._api_call("/api/call/status", params=params)
        items = result if isinstance(result, list) else result.get("sessions", [])
        return [CallSession.from_dict(item) for item in items]

    async def dial(self, number: str) -> int | None:
        """Start an outgoing call and return the new session id."""
        result = await self._api_call("/api/call/dial", params={"number": number})
        return result.get("session")

    async def answer_call(self, session: int) -> None:
        """Answer an incoming call."""
        await self._api_call("/api/call/answer", params={"session": session})

    async def hangup_call(self, session: int, reason: str | None = None) -> None:
        """Hang up a call. Reason is normal, rejected or busy."""
        params: dict[str, Any] = {"session": session}
        if reason:
            params["reason"] = reason
        await self._api_call("/api/call/hangup", params=params)

    # --------------------------------------------------------------- Phone --

    async def get_phone_status(self) -> list[PhoneAccount]:
        """Return the SIP account registration states."""
        result = await self._api_call("/api/phone/status")
        return [PhoneAccount.from_dict(item) for item in result.get("accounts", [])]

    # --------------------------------------------------------------- Audio --

    async def audio_test(self) -> None:
        """
        Start the automatic speaker/microphone loop test.

        The result arrives asynchronously as an AudioLoopTest event.
        """
        await self._api_call("/api/audio/test")

    # ------------------------------------------------------------- Display --

    async def display_text(
        self,
        text: str,
        *,
        uid: str | None = None,
        timeout: int | None = None,  # noqa: ASYNC109
        icon: str | None = None,
    ) -> None:
        """Show a text message on the device display (PUT /api/display/text)."""
        body: dict[str, Any] = {"text": text}
        if uid:
            body["uid"] = uid
        if timeout is not None:
            body["timeout"] = timeout
        if icon:
            body["icon"] = icon
        await self._api_call("/api/display/text", method="PUT", json=body)

    async def delete_display_text(self, uid: str | None = None) -> None:
        """Remove a text message from the device display."""
        body = {"uid": uid} if uid else None
        await self._api_call("/api/display/text", method="DELETE", json=body)

    # ---------------------------------------------------------- Automation --

    async def automation_trigger(self, trigger_id: str) -> None:
        """Fire a named HttpTrigger block in the device automation."""
        await self._api_call(
            "/api/automation/trigger", params={"triggerId": trigger_id}
        )

    # ------------------------------------------------------------- Logging --

    async def get_log_caps(self) -> list[str]:
        """Return the event types supported by the device."""
        result = await self._api_call("/api/log/caps")
        return result.get("events", [])

    async def log_subscribe(
        self,
        *,
        include: str = "new",
        filter_events: list[str] | None = None,
        duration: int = LOG_SUBSCRIPTION_DURATION,
    ) -> int:
        """Create an event subscription and return its id."""
        params: dict[str, Any] = {"include": include, "duration": duration}
        if filter_events:
            params["filter"] = ",".join(filter_events)
        result = await self._api_call("/api/log/subscribe", params=params)
        if not isinstance(result, dict) or "id" not in result:
            msg = f"Unexpected log/subscribe response: {result!r}"
            raise TwoNError(msg)
        return result["id"]

    async def log_pull(
        self,
        subscription_id: int,
        timeout: int = LOG_PULL_TIMEOUT,  # noqa: ASYNC109
    ) -> list[TwoNEvent]:
        """Long-poll for new events on a subscription."""
        result = await self._api_call(
            "/api/log/pull",
            params={"id": subscription_id, "timeout": timeout},
            timeout=LOG_PULL_HTTP_TIMEOUT,
        )
        if not isinstance(result, dict):
            msg = f"Unexpected log/pull response: {result!r}"
            raise TwoNError(msg)
        return [TwoNEvent.from_dict(item) for item in result.get("events", [])]

    async def log_unsubscribe(self, subscription_id: int) -> None:
        """Release an event subscription."""
        await self._api_call("/api/log/unsubscribe", params={"id": subscription_id})

    # ------------------------------------------------------ Event listener --

    def register_event_callback(
        self, event_callback: Callable[[TwoNEvent], None]
    ) -> None:
        """Register a callback invoked for every pulled event."""
        self._event_callbacks.append(event_callback)

    def register_auth_error_callback(self, auth_callback: Callable[[], None]) -> None:
        """Register a callback invoked when the event loop hits an auth error."""
        self._auth_error_callbacks.append(auth_callback)

    def start_event_listener(self) -> None:
        """Start the background subscribe/pull loop."""
        if self._event_task is None or self._event_task.done():
            self._event_task = asyncio.get_running_loop().create_task(
                self._event_loop()
            )

    async def stop_event_listener(self) -> None:
        """Stop the background event loop."""
        if self._event_task is not None:
            self._event_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._event_task
            self._event_task = None

    async def close(self) -> None:
        """Stop background tasks. The HTTP client is owned by the caller."""
        await self.stop_event_listener()

    async def _event_loop(self) -> None:
        """Maintain a log subscription and dispatch pulled events."""
        delay = RECONNECT_DELAY_MIN
        while True:
            subscription_id: int | None = None
            try:
                subscription_id = await self.log_subscribe()
                LOGGER.debug(
                    "Subscribed to event log on %s (id=%s)",
                    self._base,
                    subscription_id,
                )
                delay = RECONNECT_DELAY_MIN
                while True:
                    events = await self.log_pull(subscription_id)
                    for event in events:
                        self._dispatch_event(event)
            except asyncio.CancelledError:
                if subscription_id is not None:
                    with contextlib.suppress(TwoNError):
                        await self.log_unsubscribe(subscription_id)
                raise
            except (TwoNNotSupportedError, TwoNPrivilegeError) as err:
                # A privilege error means the credentials are valid but the
                # account can't read the log; neither case warrants re-auth.
                LOGGER.warning(
                    "Event logging is not available on %s (%s); "
                    "real-time events unavailable",
                    self._base,
                    err,
                )
                return
            except TwoNAuthError:
                LOGGER.warning(
                    "Authentication failed in event listener for %s", self._base
                )
                for auth_callback in self._auth_error_callbacks:
                    auth_callback()
                return
            except TwoNError as err:
                # Covers connection drops and expired subscriptions; both are
                # fixed by resubscribing after a backoff.
                LOGGER.debug(
                    "Event listener error on %s: %s; retrying in %ss",
                    self._base,
                    err,
                    delay,
                )
                await asyncio.sleep(delay)
                delay = min(delay * 2, RECONNECT_DELAY_MAX)
            except Exception:
                # The listener must never die silently on an unexpected
                # payload shape or bug; log loudly and keep retrying.
                LOGGER.exception(
                    "Unexpected error in event listener for %s; retrying in %ss",
                    self._base,
                    delay,
                )
                await asyncio.sleep(delay)
                delay = min(delay * 2, RECONNECT_DELAY_MAX)

    def _dispatch_event(self, event: TwoNEvent) -> None:
        """Invoke all registered callbacks for an event."""
        LOGGER.debug("Event from %s: %s %s", self._base, event.event, event.params)
        for event_callback in self._event_callbacks:
            try:
                event_callback(event)
            except Exception:
                LOGGER.exception("Error in event callback")
