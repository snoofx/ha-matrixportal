"""Admin panel in the sidebar and its WebSocket commands."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import voluptuous as vol

from homeassistant.components import panel_custom, websocket_api
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant, callback

from .const import COMMANDS, DESIGNS, DOMAIN, HEADER_MODES, PANEL_COMPONENT, PANEL_URL_PATH, STATIC_URL
from .link import DisplayLink, hostname
from .store import ConfigError, DeviceStore, clean_config

FRONTEND_DIR = Path(__file__).parent / "frontend"
PANEL_FILE = "matrixportal-panel.js"


def posix_tz(name: str) -> str | None:
    """POSIX TZ string (e.g. CET-1CEST,M3.5.0,M10.5.0/3) of an IANA zone: last line of its TZif file."""
    data = None
    try:
        import zoneinfo

        for base in zoneinfo.TZPATH:
            path = os.path.join(base, name)
            if os.path.isfile(path):
                data = Path(path).read_bytes()
                break
        if data is None:
            from importlib import resources

            data = resources.files("tzdata").joinpath("zoneinfo", *name.split("/")).read_bytes()
    except (ImportError, OSError, ValueError):
        return None
    if not data.startswith(b"TZif") or data[4:5] not in (b"2", b"3", b"4"):
        return None
    footer = data.rstrip(b"\n").rsplit(b"\n", 1)[-1].decode(errors="ignore").strip()
    return footer or None


async def async_register_panel(hass: HomeAssistant) -> None:
    """Adds "MatrixPortal" to the sidebar, admins only."""
    path = FRONTEND_DIR / PANEL_FILE
    await hass.http.async_register_static_paths([StaticPathConfig(STATIC_URL, str(FRONTEND_DIR), cache_headers=False)])
    mtime = int((await hass.async_add_executor_job(path.stat)).st_mtime)
    await panel_custom.async_register_panel(
        hass,
        frontend_url_path=PANEL_URL_PATH,
        webcomponent_name=PANEL_COMPONENT,
        sidebar_title="MatrixPortal",
        sidebar_icon="mdi:dots-grid",
        module_url=f"{STATIC_URL}/{PANEL_FILE}?v={mtime}",
        embed_iframe=False,
        require_admin=True,
    )


@callback
def async_register_commands(hass: HomeAssistant) -> None:
    for command in (ws_devices, ws_save_config, ws_set, ws_command, ws_rename):
        websocket_api.async_register_command(hass, command)


def _links(hass: HomeAssistant) -> list[DisplayLink]:
    return [entry.runtime_data for entry in hass.config_entries.async_loaded_entries(DOMAIN)]


def _link(hass: HomeAssistant, entry_id: str) -> DisplayLink | None:
    return next((link for link in _links(hass) if link.entry.entry_id == entry_id), None)


def _store(hass: HomeAssistant) -> DeviceStore:
    return hass.data[DOMAIN]


@websocket_api.websocket_command({vol.Required("type"): "matrixportal/devices"})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_devices(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    from .update import read_manifest

    store = _store(hass)
    manifest = await hass.async_add_executor_job(read_manifest)
    ha_tz = await hass.async_add_executor_job(posix_tz, hass.config.time_zone)
    devices = []
    for link in _links(hass):
        has = store.has(link.device_id)
        devices.append(
            {
                **link.info(),
                "config": store.config(link.device_id) if has else None,
                "password": store.password(link.device_id),
            }
        )
    devices.sort(key=lambda d: d["name"].lower())
    connection.send_result(
        msg["id"],
        {
            "devices": devices,
            "ha_tz": ha_tz,
            "firmware": manifest["version"] if manifest else None,
            "designs": list(DESIGNS),
            "headers": list(HEADER_MODES),
        },
    )


@websocket_api.websocket_command(
    {vol.Required("type"): "matrixportal/save_config", vol.Required("entry_id"): str, vol.Required("config"): dict}
)
@websocket_api.require_admin
@callback
def ws_save_config(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    link = _link(hass, msg["entry_id"])
    store = _store(hass)
    if link is None or not store.has(link.device_id):
        connection.send_error(msg["id"], "not_found", "Display not found or never connected")
        return
    try:
        config = clean_config(msg["config"])
    except ConfigError as err:
        connection.send_error(msg["id"], "invalid_format", str(err))
        return
    store.set_config(link.device_id, config)
    connection.send_result(msg["id"], {"pushed": link.push_config(), "config": config})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "matrixportal/set",
        vol.Required("entry_id"): str,
        vol.Optional("on"): bool,
        vol.Optional("brightness"): vol.All(int, vol.Range(min=1, max=255)),
        vol.Optional("demo"): bool,
        vol.Optional("design"): vol.In(DESIGNS),
        vol.Optional("header"): vol.In(HEADER_MODES),
        vol.Optional("pac_every"): vol.All(int, vol.Range(min=0, max=1440)),
    }
)
@websocket_api.require_admin
@callback
def ws_set(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    link = _link(hass, msg["entry_id"])
    values = {k: v for k, v in msg.items() if k not in ("type", "id", "entry_id")}
    if link is None or not link.set(**values):
        connection.send_error(msg["id"], "not_connected", "Display is not connected")
        return
    connection.send_result(msg["id"])


@websocket_api.websocket_command(
    {vol.Required("type"): "matrixportal/command", vol.Required("entry_id"): str, vol.Required("command"): vol.In(COMMANDS)}
)
@websocket_api.require_admin
@callback
def ws_command(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    link = _link(hass, msg["entry_id"])
    if link is None or not link.command(msg["command"]):
        connection.send_error(msg["id"], "not_connected", "Display is not connected")
        return
    connection.send_result(msg["id"])


@websocket_api.websocket_command(
    {vol.Required("type"): "matrixportal/rename", vol.Required("entry_id"): str,
     vol.Required("name"): vol.All(str, vol.Length(min=1, max=31))}
)
@websocket_api.require_admin
@callback
def ws_rename(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    """The display takes the name as hostname and restarts (update listener of the entry)."""
    link = _link(hass, msg["entry_id"])
    if link is None:
        connection.send_error(msg["id"], "not_found", "Display not found")
        return
    hass.config_entries.async_update_entry(link.entry, title=hostname(msg["name"]))
    connection.send_result(msg["id"], {"name": link.entry.title})
