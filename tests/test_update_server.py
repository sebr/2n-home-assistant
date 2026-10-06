"""Tests for the 2N firmware update server client."""

from __future__ import annotations

from dataclasses import replace
from importlib import import_module

import httpx
import pytest
import respx

from .conftest import SYSTEM_INFO

_update_server = import_module("custom_components.2n_intercom.hapi.update_server")
get_newest_firmware = _update_server.get_newest_firmware
_exceptions = import_module("custom_components.2n_intercom.hapi.exceptions")
TwoNConnectionError = _exceptions.TwoNConnectionError
TwoNError = _exceptions.TwoNError

INFO = replace(SYSTEM_INFO, sw_version="3.2.0.79.2", firmware_package="verso2")
URL = "https://update.2n.cz/hip/verso2/newest/"

NEWEST = {
    "files": [
        {
            "type": "firmware",
            "url": "https://update.2n.cz/api/downloads/2bd41ee3",
            "checksum": "f54f0776",
        }
    ],
    "package_lang": "en",
    "version": "3.3.1.82.4",
    "changelog.md": [
        {"version": "3.3.0.82.2", "language": "EN", "text": "### 3.3.0"},
        {"version": "3.3.1.82.4", "language": "EN", "text": "### 3.3.1"},
    ],
}


@respx.mock
async def test_newer_firmware() -> None:
    """A 200 reply parses into the newest release."""
    route = respx.get(URL).respond(json=NEWEST)
    async with httpx.AsyncClient() as client:
        release = await get_newest_firmware(client, INFO)

    assert route.calls.last.request.url.params["current_ver"] == "3.2.0.79.2"
    assert route.calls.last.request.url.params["ui_lang"] == "en"
    assert release.version == "3.3.1.82.4"
    assert release.download_url == "https://update.2n.cz/api/downloads/2bd41ee3"
    assert release.checksum == "f54f0776"
    assert [entry.version for entry in release.changelog] == [
        "3.3.0.82.2",
        "3.3.1.82.4",
    ]


@respx.mock
async def test_up_to_date() -> None:
    """A 204 reply means the device already runs the newest firmware."""
    respx.get(URL).respond(status_code=204)
    async with httpx.AsyncClient() as client:
        assert await get_newest_firmware(client, INFO) is None


@respx.mock
async def test_unknown_package() -> None:
    """A 404 for an unknown firmware package raises."""
    respx.get(URL).respond(status_code=404)
    async with httpx.AsyncClient() as client:
        with pytest.raises(TwoNError, match="HTTP 404"):
            await get_newest_firmware(client, INFO)


@respx.mock
async def test_malformed_reply() -> None:
    """A reply without a version raises."""
    respx.get(URL).respond(json={"files": []})
    async with httpx.AsyncClient() as client:
        with pytest.raises(TwoNError, match="Unexpected reply"):
            await get_newest_firmware(client, INFO)


@respx.mock
async def test_connection_error() -> None:
    """Network failures raise a connection error."""
    respx.get(URL).mock(side_effect=httpx.ConnectError("boom"))
    async with httpx.AsyncClient() as client:
        with pytest.raises(TwoNConnectionError):
            await get_newest_firmware(client, INFO)


async def test_missing_package() -> None:
    """Devices that don't report a firmware package can't be looked up."""
    async with httpx.AsyncClient() as client:
        with pytest.raises(TwoNError, match="firmware package"):
            await get_newest_firmware(client, SYSTEM_INFO)
