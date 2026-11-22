"""Design, header, view, effect and screensaver of the display, switchable live."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import MatrixConfigEntry
from .const import DESIGNS, EFFECTS, HEADER_MODES, SAVER_MODES, VIEWS
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
            DisplaySelect(link, "view", list(VIEWS), "mdi:television-guide", config=False),
            DisplaySelect(link, "effect", list(EFFECTS), "mdi:auto-fix", config=False),
            DisplaySelect(link, "saver", list(SAVER_MODES), "mdi:sleep"),
            DisplaySelect(link, "saver_view", list(VIEWS[1:]), "mdi:television-ambient-light"),
        ]
    )


class DisplaySelect(MatrixEntity, SelectEntity):
    def __init__(self, link: DisplayLink, key: str, options: list[str], icon: str, config: bool = True) -> None:
        super().__init__(link, key)
        self._attr_entity_category = EntityCategory.CONFIG if config else None
        self._key = key
        self._attr_options = options
        self._attr_icon = icon

    @property
    def available(self) -> bool:
        # Firmware ohne diese Einstellung (vor 1.2) schickt den Wert nicht
        return super().available and self._key in self._status

    @property
    def current_option(self) -> str | None:
        value = self._status.get(self._key)
        return value if value in self.options else None

    async def async_select_option(self, option: str) -> None:
        self._link.set(**{self._key: option})
