"""The display as a dimmable light: on/off and brightness."""

from __future__ import annotations

from typing import Any

from homeassistant.components.light import ATTR_BRIGHTNESS, ColorMode, LightEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import MatrixConfigEntry
from .entity import MatrixEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: MatrixConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities([DisplayLight(entry.runtime_data, "display")])


class DisplayLight(MatrixEntity, LightEntity):
    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}
    _attr_icon = "mdi:television-ambient-light"

    @property
    def is_on(self) -> bool | None:
        return self._status.get("on")

    @property
    def brightness(self) -> int | None:
        return self._status.get("brightness")

    async def async_turn_on(self, **kwargs: Any) -> None:
        values: dict[str, Any] = {"on": True}
        if ATTR_BRIGHTNESS in kwargs:
            values["brightness"] = max(1, int(kwargs[ATTR_BRIGHTNESS]))
        self._link.set(**values)

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._link.set(on=False)
