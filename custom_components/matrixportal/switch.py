"""Demo mode (not stored on the display) and LED strip following the effect."""

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
    async_add_entities([DemoSwitch(entry.runtime_data, "demo"), StripFollowSwitch(entry.runtime_data, "strip_follow")])


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


class StripFollowSwitch(MatrixEntity, SwitchEntity):
    """The LED strip takes the color of the effect while one is shown."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:led-strip-variant"

    @property
    def available(self) -> bool:
        return super().available and "strip_follow" in self._status

    @property
    def is_on(self) -> bool | None:
        return self._status.get("strip_follow")

    async def async_turn_on(self, **kwargs: Any) -> None:
        self._link.set(strip_follow=True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._link.set(strip_follow=False)
