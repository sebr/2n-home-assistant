"""
Client for 2N's firmware update server.

The device's web interface asks this server for the newest firmware. 2N does
not document it, so callers should treat any failure as "no update info".
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx

from .exceptions import TwoNConnectionError, TwoNError
from .models import FirmwareRelease

if TYPE_CHECKING:
    from .models import SystemInfo

UPDATE_SERVER = "https://update.2n.cz"
UPDATE_SERVER_TIMEOUT = 10.0


async def get_newest_firmware(
    client: httpx.AsyncClient,
    info: SystemInfo,
    language: str = "en",
) -> FirmwareRelease | None:
    """
    Return the newest firmware for a device, or None if it is up to date.

    The server picks the firmware family from ``info.firmware_package`` and
    returns release notes for every version newer than ``info.sw_version``.
    """
    if not info.firmware_package or not info.sw_version:
        msg = "Device does not report its firmware package and version"
        raise TwoNError(msg)

    url = f"{UPDATE_SERVER}/hip/{info.firmware_package}/newest/"
    params = {"current_ver": info.sw_version, "ui_lang": language}
    try:
        response = await client.get(url, params=params, timeout=UPDATE_SERVER_TIMEOUT)
    except httpx.HTTPError as err:
        msg = f"Error connecting to {UPDATE_SERVER}: {err}"
        raise TwoNConnectionError(msg) from err

    if response.status_code == httpx.codes.NO_CONTENT:
        return None
    if response.status_code != httpx.codes.OK:
        msg = f"Update server returned HTTP {response.status_code} for {url}"
        raise TwoNError(msg)

    try:
        return FirmwareRelease.from_dict(response.json())
    except (ValueError, KeyError, TypeError, AttributeError) as err:
        msg = f"Unexpected reply from update server: {err}"
        raise TwoNError(msg) from err
