"""Design and header of the display, switchable live (to compare designs)."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import MatrixConfigEntry
from .const import DESIGNS, HEADER_MODES
from .entity import MatrixEntity
from .link import DisplayLink


async def async_setup_entry(
    hass: HomeAssistant, entry: MatrixConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    link = entry.runtime_data
    async_add_entities(
        [
            DisplaySelect(link, "design", list(DESIGNS), "mdi:view-dashboard-variant"),
            DisplaySelect(link, "header", list(HEADER_MODES), "mdi:page-layout-header"),
        ]
    )


class DisplaySelect(MatrixEntity, SelectEntity):
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, link: DisplayLink, key: str, options: list[str], icon: str) -> None:
        super().__init__(link, key)
        self._key = key
        self._attr_options = options
        self._attr_icon = icon

    @property
    def current_option(self) -> str | None:
        value = self._status.get(self._key)
        return value if value in self.options else None

    async def async_select_option(self, option: str) -> None:
        self._link.set(**{self._key: option})
