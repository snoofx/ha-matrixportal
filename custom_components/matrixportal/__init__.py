"""MatrixPortal: 192×64 LED display managed by Home Assistant.

Displays are found by mDNS. HA pairs with each one, sends it its configuration (entities,
calendars, header), the states it shows and the events of its calendars, and offers entities to
control it. Configuration in the sidebar panel "MatrixPortal" (admins only).
"""

from __future__ import annotations

import logging

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .api import async_register_commands, async_register_panel
from .const import CONF_LINK_KEY, DOMAIN
from .link import DisplayLink, async_unpair
from .store import DeviceStore

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.LIGHT,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.TIME,
    Platform.UPDATE,
]

type MatrixConfigEntry = ConfigEntry[DisplayLink]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    store = DeviceStore(hass)
    await store.async_load()
    hass.data[DOMAIN] = store
    async_register_commands(hass)
    await async_register_panel(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: MatrixConfigEntry) -> bool:
    link = DisplayLink(hass, entry, hass.data[DOMAIN])
    entry.runtime_data = link
    link.update_device()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    link.start()
    entry.async_on_unload(entry.add_update_listener(_async_entry_updated))
    return True


async def _async_entry_updated(hass: HomeAssistant, entry: MatrixConfigEntry) -> None:
    """Renamed in HA (entry title): the display follows."""
    if entry.runtime_data.name != entry.title:
        entry.runtime_data.push_name()


async def async_unload_entry(hass: HomeAssistant, entry: MatrixConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: MatrixConfigEntry) -> None:
    """A removed display loses its stored configuration and is unpaired, so it can be added again."""
    store: DeviceStore | None = hass.data.get(DOMAIN)
    if store is not None and entry.unique_id:
        store.remove(entry.unique_id)
    try:
        await async_unpair(hass, entry.data[CONF_HOST], entry.data[CONF_LINK_KEY])
    except (aiohttp.ClientError, TimeoutError, OSError, ValueError) as err:
        _LOGGER.warning(
            "%s could not be unpaired (%s). Use System in its web UI, or hold UP and DOWN at power-on",
            entry.title, err,
        )
