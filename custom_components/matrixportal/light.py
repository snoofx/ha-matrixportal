"""The display as a dimmable light (on/off, brightness) and the LED strip at A2 as an RGB light."""

from __future__ import annotations

from typing import Any

from homeassistant.components.light import ATTR_BRIGHTNESS, ATTR_RGB_COLOR, ColorMode, LightEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import MatrixConfigEntry
from .entity import MatrixEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: MatrixConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities([DisplayLight(entry.runtime_data, "display"), StripLight(entry.runtime_data, "strip")])


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


class StripLight(MatrixEntity, LightEntity):
    """One color for the whole strip. Older firmware sends no strip_* status: unavailable."""

    _attr_color_mode = ColorMode.RGB
    _attr_supported_color_modes = {ColorMode.RGB}
    _attr_icon = "mdi:led-strip-variant"

    @property
    def available(self) -> bool:
        return super().available and "strip_on" in self._status

    @property
    def is_on(self) -> bool | None:
        return self._status.get("strip_on")

    @property
    def brightness(self) -> int | None:
        return self._status.get("strip_brightness")

    @property
    def rgb_color(self) -> tuple[int, int, int] | None:
        rgb = self._status.get("strip_rgb")
        return tuple(rgb) if rgb else None

    async def async_turn_on(self, **kwargs: Any) -> None:
        values: dict[str, Any] = {"strip_on": True}
        if ATTR_BRIGHTNESS in kwargs:
            values["strip_brightness"] = max(1, int(kwargs[ATTR_BRIGHTNESS]))
        if ATTR_RGB_COLOR in kwargs:
            values["strip_rgb"] = [int(c) for c in kwargs[ATTR_RGB_COLOR]]
        self._link.set(**values)

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._link.set(strip_on=False)
