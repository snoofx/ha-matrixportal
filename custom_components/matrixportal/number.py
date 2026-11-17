"""Pac-Man interval in minutes (0 = off)."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import MatrixConfigEntry
from .entity import MatrixEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: MatrixConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities([PacInterval(entry.runtime_data, "pac_every")])


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
