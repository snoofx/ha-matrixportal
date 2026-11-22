"""Screensaver time window (from / to) as time entities."""

from __future__ import annotations

from datetime import time

from homeassistant.components.time import TimeEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import MatrixConfigEntry
from .entity import MatrixEntity
from .link import DisplayLink


async def async_setup_entry(
    hass: HomeAssistant, entry: MatrixConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    link = entry.runtime_data
    async_add_entities([SaverTime(link, "saver_from"), SaverTime(link, "saver_to")])


class SaverTime(MatrixEntity, TimeEntity):
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:clock-outline"

    def __init__(self, link: DisplayLink, key: str) -> None:
        super().__init__(link, key)
        self._key = key

    @property
    def available(self) -> bool:
        return super().available and self._key in self._status

    @property
    def native_value(self) -> time | None:
        value = self._status.get(self._key)
        try:
            hours, minutes = (int(p) for p in str(value).split(":")[:2])
            return time(hours, minutes)
        except (TypeError, ValueError):
            return None

    async def async_set_value(self, value: time) -> None:
        self._link.set(**{self._key: value.strftime("%H:%M")})
