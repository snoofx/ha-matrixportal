"""Display configurations and passwords, stored in Home Assistant."""

from __future__ import annotations

import copy
import hashlib
import json
import re
import secrets
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import (
    DEFAULT_CONFIG,
    MAX_BLOCKERS,
    MAX_CALENDARS,
    MAX_ENTITY,
    MAX_INFO,
    MAX_LABEL,
    MAX_TZ,
    PASSWORD_LENGTH,
    STORAGE_KEY,
    STORAGE_VERSION,
)

ENTITY_RE = re.compile(r"^[a-z0-9_]+\.[a-z0-9_]+$")


class ConfigError(ValueError):
    """A configuration the display cannot take."""


def _entity(value: Any, key: str, domains: tuple[str, ...] | None = None) -> str:
    if value in (None, ""):
        return ""
    if not isinstance(value, str) or not ENTITY_RE.match(value) or len(value) > MAX_ENTITY:
        raise ConfigError(f"{key}: no valid entity id")
    if domains and value.split(".", 1)[0] not in domains:
        raise ConfigError(f"{key}: must be one of {', '.join(domains)}")
    return value


def _number(value: Any, key: str, default: int) -> int:
    if value is None:
        return default
    try:
        number = int(value)
    except (TypeError, ValueError) as err:
        raise ConfigError(f"{key}: no number") from err
    if not 100 <= number <= 65000:
        raise ConfigError(f"{key}: 100 to 65000")
    return number


def clean_config(config: Any) -> dict[str, Any]:
    """Checks a configuration from the panel or the display, fills in defaults."""
    if not isinstance(config, dict):
        raise ConfigError("configuration must be an object")
    out: dict[str, Any] = copy.deepcopy(DEFAULT_CONFIG)
    out["solar"] = _entity(config.get("solar"), "solar", ("sensor",))
    out["office"] = _entity(config.get("office"), "office", ("sensor",))
    out["room"] = _entity(config.get("room"), "room", ("sensor", "climate"))
    out["weather"] = _entity(config.get("weather"), "weather", ("weather",))
    out["work_calendar"] = _entity(config.get("work_calendar"), "work_calendar", ("calendar",))
    calendars = config.get("calendars") or []
    if not isinstance(calendars, list):
        raise ConfigError("calendars: list expected")
    out["calendars"] = list(dict.fromkeys(_entity(c, "calendars", ("calendar",)) for c in calendars if c))
    if len(",".join(out["calendars"])) > MAX_CALENDARS:
        raise ConfigError(f"calendars: at most {MAX_CALENDARS} characters together")
    info = config.get("info") or []
    if not isinstance(info, list) or len(info) > MAX_INFO:
        raise ConfigError(f"info: at most {MAX_INFO} entries")
    out["info"] = []
    for item in info:
        if not isinstance(item, dict):
            raise ConfigError("info: entries need entity and label")
        entity = _entity(item.get("entity"), "info")
        label = str(item.get("label") or "").strip()
        if len(label.encode()) > MAX_LABEL:
            raise ConfigError(f"info: label at most {MAX_LABEL} characters")
        if entity:
            out["info"].append({"entity": entity, "label": label})
    for key, limit in (("blockers", MAX_BLOCKERS), ("tz", MAX_TZ)):
        value = config.get(key, out[key])
        if not isinstance(value, str) or len(value.encode()) > limit:
            raise ConfigError(f"{key}: text up to {limit} characters")
        out[key] = value.strip()
    out["solar_max"] = _number(config.get("solar_max"), "solar_max", 800)
    out["office_max"] = _number(config.get("office_max"), "office_max", 400)
    return out


def config_revision(config: dict[str, Any]) -> str:
    """Short hash the display stores with its configuration, so an unchanged one is not resent."""
    text = json.dumps(config, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha1(text.encode()).hexdigest()[:12]


def watched_entities(config: dict[str, Any]) -> list[str]:
    """Entities whose states the display shows (same order as watchList() in the firmware)."""
    found = [config.get(k) for k in ("solar", "office", "room", "weather")]
    found += [item["entity"] for item in config.get("info", [])]
    return list(dict.fromkeys(e for e in found if e))


def config_calendars(config: dict[str, Any]) -> set[str]:
    """The only calendars the display may read."""
    found = set(config.get("calendars", []))
    if config.get("work_calendar"):
        found.add(config["work_calendar"])
    return found


class DeviceStore:
    """Configuration and password of every display of this HA, by device id (MAC)."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self.devices: dict[str, dict[str, Any]] = {}

    async def async_load(self) -> None:
        data = await self._store.async_load() or {}
        self.devices = data.get("devices", {})

    def _save(self) -> None:
        self._store.async_delay_save(lambda: {"devices": self.devices}, 1)

    def has(self, device_id: str) -> bool:
        return device_id in self.devices

    def adopt(self, device_id: str, config: dict[str, Any]) -> None:
        """First contact: the display's own configuration is taken over, nothing gets lost."""
        self.devices[device_id] = {
            "config": config,
            "password": secrets.token_urlsafe(PASSWORD_LENGTH)[:PASSWORD_LENGTH],
        }
        self._save()

    def config(self, device_id: str) -> dict[str, Any]:
        return copy.deepcopy(self.devices[device_id]["config"])

    def set_config(self, device_id: str, config: dict[str, Any]) -> None:
        self.devices[device_id]["config"] = config
        self._save()

    def password(self, device_id: str) -> str:
        device = self.devices.get(device_id)
        return device["password"] if device else ""

    def remove(self, device_id: str) -> None:
        if self.devices.pop(device_id, None) is not None:
            self._save()
