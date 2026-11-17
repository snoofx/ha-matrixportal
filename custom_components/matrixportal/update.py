"""Display firmware: the integration package carries the matching firmware and installs it through
the upload of the display (POST /update, raw image), like its web UI does."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
from pathlib import Path
from typing import Any

import aiohttp

from homeassistant.components.update import UpdateDeviceClass, UpdateEntity, UpdateEntityFeature
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import MatrixConfigEntry
from .entity import MatrixEntity
from .link import DisplayLink

# Written by tools/bundle_ha.sh: firmware.json with version and md5, and the image.
FIRMWARE_DIR = Path(__file__).parent / "firmware"
RELEASES_URL = "https://github.com/snoofx/ha-matrixportal/releases"
UPLOAD_TIMEOUT = 180
RESTART_TIMEOUT = 90


def plain_version(version: str | None) -> str | None:
    """"v1.0.0+abc1234" -> "1.0.0"."""
    if not version:
        return None
    return version.removeprefix("v").split("+", 1)[0]


def read_manifest() -> dict[str, Any] | None:
    path = FIRMWARE_DIR / "firmware.json"
    if not path.exists():
        return None  # development checkout without bundled firmware
    return json.loads(path.read_text())


async def async_upload_firmware(hass: HomeAssistant, host: str, password: str, image: bytes) -> None:
    """Sends the image; the display restarts into it and rolls back without 30 s of WiFi."""
    headers = {"Content-Type": "application/octet-stream"}
    if password:
        headers["Authorization"] = "Basic " + base64.b64encode(f"admin:{password}".encode()).decode()
    session = async_get_clientsession(hass)
    try:
        async with asyncio.timeout(UPLOAD_TIMEOUT):
            async with session.post(f"http://{host}/update", data=image, headers=headers) as response:
                text = (await response.text()).strip()
    except (aiohttp.ClientError, TimeoutError) as err:
        raise HomeAssistantError(f"Upload to the display failed: {err}") from err
    if response.status == 401:
        raise HomeAssistantError("The display refused the password")
    if response.status != 200:
        raise HomeAssistantError(text or f"HTTP {response.status}")


async def async_setup_entry(
    hass: HomeAssistant, entry: MatrixConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    manifest = await hass.async_add_executor_job(read_manifest)
    async_add_entities([Firmware(entry.runtime_data, manifest)])


class Firmware(MatrixEntity, UpdateEntity):
    _attr_device_class = UpdateDeviceClass.FIRMWARE
    _attr_entity_category = EntityCategory.CONFIG
    _attr_supported_features = UpdateEntityFeature.INSTALL | UpdateEntityFeature.PROGRESS
    _attr_title = "MatrixPortal Firmware"
    _attr_release_url = RELEASES_URL

    def __init__(self, link: DisplayLink, manifest: dict[str, Any] | None) -> None:
        super().__init__(link, "firmware")
        self._manifest = manifest

    @property
    def available(self) -> bool:
        return self._link.version is not None

    @property
    def installed_version(self) -> str | None:
        return plain_version(self._link.version)

    @property
    def latest_version(self) -> str | None:
        return self._manifest["version"] if self._manifest else self.installed_version

    async def async_install(self, version: str | None, backup: bool, **kwargs: Any) -> None:
        if self._manifest is None:
            raise HomeAssistantError("This installation of the integration carries no firmware")
        image = await self.hass.async_add_executor_job((FIRMWARE_DIR / self._manifest["file"]).read_bytes)
        if hashlib.md5(image).hexdigest() != self._manifest["md5"]:
            raise HomeAssistantError("Firmware file is damaged, reinstall the integration")
        link = self._link
        target = self._manifest["version"]
        hellos = link.hellos
        self._attr_in_progress = True
        self.async_write_ha_state()
        try:
            await async_upload_firmware(self.hass, link.host, link.store.password(link.device_id), image)
            async with asyncio.timeout(RESTART_TIMEOUT):
                while link.hellos == hellos or plain_version(link.version) != target:
                    await asyncio.sleep(1)
        except TimeoutError as err:
            raise HomeAssistantError(
                f"The display did not come back with {target}, it reports {link.version}"
            ) from err
        finally:
            self._attr_in_progress = False
            self.async_write_ha_state()
