"""Demo mode: fake events and values, not stored on the display."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import MatrixConfigEntry
from .entity import MatrixEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: MatrixConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities([DemoSwitch(entry.runtime_data, "demo")])


class DemoSwitch(MatrixEntity, SwitchEntity):
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:presentation-play"

    @property
    def is_on(self) -> bool | None:
        return self._status.get("demo")

    async def async_turn_on(self, **kwargs: Any) -> None:
        self._link.set(demo=True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._link.set(demo=False)
