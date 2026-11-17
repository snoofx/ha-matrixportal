"""Diagnostics of the display: WiFi signal, events today, start time, free memory."""

from __future__ import annotations

from datetime import datetime, timedelta

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import SIGNAL_STRENGTH_DECIBELS_MILLIWATT, EntityCategory, UnitOfInformation
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from . import MatrixConfigEntry
from .entity import MatrixEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: MatrixConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    link = entry.runtime_data
    async_add_entities([Rssi(link, "rssi"), Events(link, "events"), Started(link, "started"), Heap(link, "heap")])


class Rssi(MatrixEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.SIGNAL_STRENGTH
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = SIGNAL_STRENGTH_DECIBELS_MILLIWATT
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self):
        return self._status.get("rssi")


class Events(MatrixEntity, SensorEntity):
    _attr_icon = "mdi:calendar-today"
    _attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self):
        return self._status.get("events")

    @property
    def extra_state_attributes(self) -> dict:
        # 1 ok, -1 failed, 2 none configured, 0 not yet
        return {"calendar_status": self._status.get("calendar")}


class Started(MatrixEntity, SensorEntity):
    """Start time from the uptime; kept unless it moves by more than two minutes (jitter)."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _started: datetime | None = None

    @property
    def native_value(self) -> datetime | None:
        uptime = self._status.get("uptime")
        if not isinstance(uptime, (int, float)):
            return self._started
        started = dt_util.utcnow() - timedelta(seconds=uptime)
        if self._started is None or abs((started - self._started).total_seconds()) > 120:
            self._started = started.replace(microsecond=0)
        return self._started


class Heap(MatrixEntity, SensorEntity):
    _attr_native_unit_of_measurement = UnitOfInformation.BYTES
    _attr_device_class = SensorDeviceClass.DATA_SIZE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False

    @property
    def native_value(self):
        return self._status.get("heap")
