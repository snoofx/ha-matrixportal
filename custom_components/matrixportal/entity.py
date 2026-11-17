"""Base of all entities of a display."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from .const import DOMAIN, SIGNAL_UPDATED
from .link import DisplayLink


class MatrixEntity(Entity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, link: DisplayLink, key: str) -> None:
        self._link = link
        self._attr_unique_id = f"{link.device_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, link.device_id)})

    @property
    def available(self) -> bool:
        return self._link.connected

    @property
    def _status(self) -> dict:
        return self._link.status

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, SIGNAL_UPDATED.format(self._link.entry.entry_id), self.async_write_ha_state
            )
        )
