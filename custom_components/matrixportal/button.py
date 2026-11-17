"""Buttons: restart, identify, Pac-Man, week overview, reload calendars."""

from __future__ import annotations

from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import MatrixConfigEntry
from .entity import MatrixEntity
from .link import DisplayLink

# key, command, device class, category, icon
BUTTONS = (
    ("restart", "restart", ButtonDeviceClass.RESTART, EntityCategory.CONFIG, None),
    ("identify", "identify", ButtonDeviceClass.IDENTIFY, EntityCategory.DIAGNOSTIC, None),
    ("pacman", "pacman", None, None, "mdi:pac-man"),
    ("week", "week", None, None, "mdi:calendar-week"),
    ("refresh", "refresh", None, EntityCategory.DIAGNOSTIC, "mdi:calendar-refresh"),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: MatrixConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities(DisplayButton(entry.runtime_data, *spec) for spec in BUTTONS)


class DisplayButton(MatrixEntity, ButtonEntity):
    def __init__(self, link: DisplayLink, key, command, device_class, category, icon) -> None:
        super().__init__(link, key)
        self._command = command
        self._attr_device_class = device_class
        self._attr_entity_category = category
        if icon:
            self._attr_icon = icon

    async def async_press(self) -> None:
        self._link.command(self._command)
