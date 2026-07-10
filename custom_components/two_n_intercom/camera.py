"""Camera platform for the 2N Intercom integration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.camera import Camera
from homeassistant.helpers.aiohttp_client import async_aiohttp_proxy_stream

from .const import LOGGER
from .entity import TwoNEntity
from .hapi.exceptions import TwoNError

if TYPE_CHECKING:
    import httpx
    from aiohttp import web
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import TwoNUpdateCoordinator
    from .data import TwoNConfigEntry

MJPEG_FPS = 5


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001
    entry: TwoNConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the camera platform."""
    coordinator = entry.runtime_data
    if coordinator.has_camera:
        async_add_entities([TwoNCamera(coordinator)])


class _HttpxStreamReader:
    """Adapt an httpx streaming response to the read() API of a StreamReader."""

    def __init__(self, response: httpx.Response) -> None:
        self._iterator = response.aiter_raw()

    async def read(self, _n: int = -1) -> bytes:
        try:
            return await anext(self._iterator)
        except StopAsyncIteration:
            return b""


class TwoNCamera(TwoNEntity, Camera):
    """Camera backed by /api/camera/snapshot (stills and MJPEG)."""

    _attr_name = None  # Use the device name.

    def __init__(self, coordinator: TwoNUpdateCoordinator) -> None:
        """Initialize the camera."""
        TwoNEntity.__init__(self, coordinator, "camera")
        Camera.__init__(self)
        caps = coordinator.camera_caps
        self._resolutions = sorted(
            caps.jpeg_resolutions if caps else [],
            key=lambda resolution: resolution[0] * resolution[1],
        )

    def _best_resolution(
        self, width: int | None, height: int | None
    ) -> tuple[int, int]:
        """
        Pick the largest supported resolution fitting the request.

        The device rejects width/height pairs that are not an exact entry
        of its jpegResolution caps, so always answer from that list.
        """
        if not self._resolutions:
            return (640, 480)
        if width is None and height is None:
            return self._resolutions[-1]
        fitting = [
            resolution
            for resolution in self._resolutions
            if (width is None or resolution[0] <= width)
            and (height is None or resolution[1] <= height)
        ]
        return fitting[-1] if fitting else self._resolutions[0]

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        """Return a JPEG snapshot from the intercom camera."""
        snapshot_width, snapshot_height = self._best_resolution(width, height)
        try:
            return await self.coordinator.api.get_camera_snapshot(
                width=snapshot_width, height=snapshot_height
            )
        except TwoNError as err:
            LOGGER.warning("Failed to fetch camera snapshot: %s", err)
            return None

    async def handle_async_mjpeg_stream(
        self, request: web.Request
    ) -> web.StreamResponse | None:
        """Proxy the device's native MJPEG stream to the browser."""
        width, height = self._best_resolution(None, None)
        try:
            async with self.coordinator.api.stream_camera(
                width=width, height=height, fps=MJPEG_FPS
            ) as response:
                content_type = response.headers.get("content-type", "")
                if response.status_code != 200 or "multipart" not in content_type:
                    LOGGER.debug(
                        "MJPEG stream unavailable (HTTP %s, %s); falling back "
                        "to snapshot polling",
                        response.status_code,
                        content_type,
                    )
                    return await super().handle_async_mjpeg_stream(request)
                return await async_aiohttp_proxy_stream(
                    self.hass,
                    request,
                    _HttpxStreamReader(response),
                    content_type,
                )
        except TwoNError as err:
            LOGGER.warning("Failed to open MJPEG stream: %s", err)
            return await super().handle_async_mjpeg_stream(request)
