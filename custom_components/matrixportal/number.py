"""Pac-Man interval in minutes (0 = off), number of pixels of the LED strip, doorbell duration."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import MatrixConfigEntry
from .const import STRIP_MAX
from .entity import MatrixEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: MatrixConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    link = entry.runtime_data
    async_add_entities([PacInterval(link, "pac_every"), StripCount(link, "strip_count"), DoorbellDuration(link, "doorbell_sec")])


class PacInterval(MatrixEntity, NumberEntity):
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:pac-man"
    _attr_native_min_value = 0
    _attr_native_max_value = 1440
    _attr_native_step = 1
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_mode = NumberMode.BOX

    @property
    def native_value(self) -> float | None:
        return self._status.get("pac_every")

    async def async_set_native_value(self, value: float) -> None:
        self._link.set(pac_every=int(value))


class StripCount(MatrixEntity, NumberEntity):
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:led-strip-variant"
    _attr_native_min_value = 0
    _attr_native_max_value = STRIP_MAX
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX

    @property
    def available(self) -> bool:
        return super().available and "strip_count" in self._status

    @property
    def native_value(self) -> float | None:
        return self._status.get("strip_count")

    async def async_set_native_value(self, value: float) -> None:
        self._link.set(strip_count=int(value))


class DoorbellDuration(MatrixEntity, NumberEntity):
    """How long waves or frame are shown. The flash style is always short."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:timer-outline"
    _attr_native_min_value = 3
    _attr_native_max_value = 120
    _attr_native_step = 1
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_mode = NumberMode.BOX

    @property
    def available(self) -> bool:
        return super().available and "doorbell_sec" in self._status

    @property
    def native_value(self) -> float | None:
        return self._status.get("doorbell_sec")

    async def async_set_native_value(self, value: float) -> None:
        self._link.set(doorbell_sec=int(value))
