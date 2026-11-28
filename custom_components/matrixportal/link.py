"""Connection from Home Assistant to one display.

HA connects to the display (ws://<display>:81/). The display says hello with its id, its
configuration and revision. HA pairs it (first contact) or proves the pairing key, sends the
configuration if the display's one is outdated, then "welcome" and the states of the entities it
shows. From then on HA relays state changes, answers calendar requests and sends commands; the
display reports its status (on, brightness, design ...).
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
import hashlib
import hmac
import json
import logging
import time
from typing import Any

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, __version__ as HA_VERSION
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, State, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
from homeassistant.helpers.json import json_dumps
from homeassistant.util import slugify
import voluptuous as vol

from .const import (
    CONF_LINK_KEY,
    CONF_PAIR_PASSWORD,
    DOMAIN,
    FORWARDED_ATTRIBUTES,
    LINK_PORT,
    MAX_CALENDAR_BYTES,
    MAX_EVENTS,
    PROTOCOL,
    SIGNAL_UPDATED,
)
from .store import ConfigError, DeviceStore, clean_config, config_calendars, config_revision, watched_entities

_LOGGER = logging.getLogger(__name__)

CONNECT_TIMEOUT = 10
LINK_CONNECT_TIMEOUT = 4
RETRY_FAST = 1
FAST_PHASE = 120
RETRY_MIN = 2
RETRY_MAX = 60
HEARTBEAT = 10
MAX_MESSAGE = 64 * 1024
FORECAST_EVERY = timedelta(minutes=30)
FORECAST_MIN_GAP = 300  # s: a weather state change refreshes the forecast at most this often


def hostname(name: str) -> str:
    """Display name as the display uses it: hostname, a-z 0-9 and "-", at most 31 characters."""
    return slugify(name, separator="-")[:31].strip("-") or "matrixportal"


def link_proof(key: str, nonce: str) -> str:
    """Answer to the nonce of a hello: HMAC-SHA256 with the pairing key."""
    return hmac.new(bytes.fromhex(key), nonce.encode(), hashlib.sha256).hexdigest()


def state_payload(state: State | None, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """A state in the compressed form of subscribe_entities, only what the display uses."""
    if state is None:
        return {"s": "unavailable", "a": {}}
    attrs = {k: state.attributes[k] for k in FORWARDED_ATTRIBUTES if k in state.attributes}
    if extra:
        attrs.update(extra)
    return {"s": state.state, "a": attrs}


def _iso(value: Any) -> str:
    return value.isoformat() if hasattr(value, "isoformat") else str(value or "")


def trim_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Only the fields the display reads, short texts, and few enough for its buffer."""
    out = []
    for event in events[:MAX_EVENTS]:
        out.append(
            {
                "summary": str(event.get("summary") or "")[:60],
                "location": str(event.get("location") or "")[:40],
                "start": _iso(event.get("start")),
                "end": _iso(event.get("end")),
            }
        )
    while out and len(json_dumps(out)) > MAX_CALENDAR_BYTES:
        out.pop()  # sorted by start: the latest go first
    return out


async def async_read_hello(hass: HomeAssistant, host: str) -> dict[str, Any]:
    """Connects once and returns the display's hello. Raises on failure."""
    session = async_get_clientsession(hass)
    async with asyncio.timeout(CONNECT_TIMEOUT):
        async with session.ws_connect(f"ws://{host}:{LINK_PORT}/", max_msg_size=MAX_MESSAGE) as ws:
            msg = await ws.receive()
            hello = json.loads(msg.data) if msg.type == aiohttp.WSMsgType.TEXT else {}
            if hello.get("type") != "hello" or not hello.get("id"):
                raise ValueError("no MatrixPortal display")
            return hello


async def _async_prove(ws: aiohttp.ClientWebSocketResponse, key: str) -> bool:
    """Reads the hello and proves the key. The display only answers a wrong proof (auth_failed)."""
    msg = await ws.receive()
    hello = json.loads(msg.data) if msg.type == aiohttp.WSMsgType.TEXT else {}
    if not hello.get("paired"):
        return False
    await ws.send_str(json_dumps({"type": "auth", "hmac": link_proof(key, str(hello.get("nonce", "")))}))
    try:
        reply = await ws.receive(timeout=2)
    except TimeoutError:
        return True
    if reply.type != aiohttp.WSMsgType.TEXT:
        return False
    return json.loads(reply.data).get("type") != "auth_failed"


async def async_verify_key(hass: HomeAssistant, host: str, key: str) -> bool:
    """True if the display is paired with this key."""
    session = async_get_clientsession(hass)
    async with asyncio.timeout(CONNECT_TIMEOUT):
        async with session.ws_connect(f"ws://{host}:{LINK_PORT}/", max_msg_size=MAX_MESSAGE) as ws:
            return await _async_prove(ws, key)


async def async_unpair(hass: HomeAssistant, host: str, key: str) -> None:
    """Lets the display go: it works locally again and can be added anew."""
    session = async_get_clientsession(hass)
    async with asyncio.timeout(CONNECT_TIMEOUT):
        async with session.ws_connect(f"ws://{host}:{LINK_PORT}/", max_msg_size=MAX_MESSAGE) as ws:
            if await _async_prove(ws, key):
                await ws.send_str(json_dumps({"type": "unpair"}))
                await ws.receive(timeout=3)


class DisplayLink:
    """Keeps the connection to one display and relays between it and HA."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, store: DeviceStore) -> None:
        self.hass = hass
        self.entry = entry
        self.store = store
        self.device_id: str = entry.unique_id or ""
        self.host: str = entry.data[CONF_HOST]
        self._key: str = entry.data[CONF_LINK_KEY]
        self.name: str = entry.title
        self.mode: str | None = None
        self.version: str | None = None
        self.proto = 1
        self.connected = False
        self.auth_failed = False
        self.last_error: str | None = None
        self.hellos = 0  # counts restarts and reconnects, for the firmware update
        self.status: dict[str, Any] = {}
        self.ha_device_id: str | None = None
        self._name_requested: str | None = None
        self._wake = asyncio.Event()
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._unsubs: list[Any] = []
        self._watch: list[str] = []
        self._forecast: dict[str, Any] = {}
        self._forecast_at = 0.0
        self._warned: set[str] = set()

    # ── Status ──

    def info(self) -> dict[str, Any]:
        return {
            "entry_id": self.entry.entry_id,
            "id": self.device_id,
            "name": self.name,
            "host": self.host,
            "mode": self.mode,
            "version": self.version,
            "connected": self.connected,
            "auth_failed": self.auth_failed,
            "last_error": self.last_error,
            "status": self.status,
        }

    @callback
    def _changed(self) -> None:
        async_dispatcher_send(self.hass, SIGNAL_UPDATED.format(self.entry.entry_id))

    @callback
    def _set_connected(self, connected: bool) -> None:
        if connected != self.connected:
            self.connected = connected
            self._changed()

    # ── Connection ──

    @callback
    def start(self) -> None:
        self.entry.async_create_background_task(self.hass, self._run(), f"{DOMAIN} {self.host}")

    async def _run(self) -> None:
        session = async_get_clientsession(self.hass)
        delay = RETRY_MIN
        fast_until = time.monotonic() + FAST_PHASE
        while True:
            try:
                async with asyncio.timeout(LINK_CONNECT_TIMEOUT):
                    ws = await session.ws_connect(
                        f"ws://{self.host}:{LINK_PORT}/", heartbeat=HEARTBEAT, max_msg_size=MAX_MESSAGE
                    )
                delay = RETRY_MIN
                try:
                    await self._session(ws)
                finally:
                    await ws.close()
                    fast_until = time.monotonic() + FAST_PHASE  # it restarts, probably
            except (aiohttp.ClientError, TimeoutError, OSError) as err:
                _LOGGER.debug("%s: connection failed: %s", self.host, err)
            finally:
                self._end_session()
            if time.monotonic() < fast_until:
                wait = min(RETRY_FAST, delay)
            else:
                wait, delay = delay, min(delay * 2, RETRY_MAX)
            try:
                await asyncio.wait_for(self._wake.wait(), wait)
            except TimeoutError:
                pass
            self._wake.clear()

    @callback
    def wake(self) -> None:
        """The display announced itself (mDNS): reconnect now instead of after the pause."""
        if not self.connected:
            self._wake.set()

    async def _session(self, ws: aiohttp.ClientWebSocketResponse) -> None:
        self._ws = ws
        self._queue = asyncio.Queue()
        sender = self.entry.async_create_background_task(
            self.hass, self._sender(ws, self._queue), f"{DOMAIN} {self.host} sender"
        )
        try:
            async for msg in ws:
                if msg.type != aiohttp.WSMsgType.TEXT:
                    break
                try:
                    data = json.loads(msg.data)
                except ValueError:
                    _LOGGER.warning("%s: invalid message", self.host)
                    continue
                self._handle(data)
        finally:
            sender.cancel()

    @staticmethod
    async def _sender(ws: aiohttp.ClientWebSocketResponse, queue: asyncio.Queue[str]) -> None:
        while True:
            await ws.send_str(await queue.get())

    @callback
    def _send(self, message: dict[str, Any]) -> None:
        if self._ws is not None:
            self._queue.put_nowait(json_dumps(message))

    @callback
    def _stop_tracking(self) -> None:
        for unsub in self._unsubs:
            unsub()
        self._unsubs = []

    @callback
    def _end_session(self) -> None:
        self._ws = None
        self._stop_tracking()
        self._set_connected(False)

    # ── Messages from the display ──

    @callback
    def _handle(self, data: dict[str, Any]) -> None:
        kind = data.get("type")
        if kind == "hello":
            self._on_hello(data)
        elif kind == "status":
            self.status = {k: v for k, v in data.items() if k != "type"}
            self._changed()
        elif kind == "get_calendar":
            self.entry.async_create_task(self.hass, self._on_get_calendar(data))
        elif kind in ("config_error", "pair_error"):
            self.last_error = str(data.get("message"))
            _LOGGER.error("%s refused: %s", self.name, self.last_error)
            self._changed()
        elif kind == "auth_failed":
            if not self.auth_failed:
                _LOGGER.error(
                    "%s is paired with another Home Assistant. Unpair it in its web UI (System) or hold "
                    "UP and DOWN at power-on, then it pairs with this one",
                    self.name,
                )
            self.auth_failed = True
            self._changed()
        elif kind == "paired":
            _LOGGER.info("%s paired with this Home Assistant", self.name)

    @callback
    def _on_hello(self, hello: dict[str, Any]) -> None:
        self._stop_tracking()
        self._set_connected(False)
        self.mode = hello.get("mode")
        self.version = hello.get("version")
        proto = hello.get("proto", 1)
        self.proto = proto if isinstance(proto, int) and proto >= 1 else 1
        self.hellos += 1
        self.update_device()
        self._changed()

        if not hello.get("paired"):
            # Fresh or unpaired display: it takes the key, then says hello again.
            self._send({"type": "pair", "key": self._key, "password": self.entry.data.get(CONF_PAIR_PASSWORD, "")})
            return
        self._send({"type": "auth", "hmac": link_proof(self._key, str(hello.get("nonce", "")))})
        self.auth_failed = False

        if self._rename(str(hello.get("name", ""))):
            return  # the display restarts with the new hostname

        if not self.store.has(self.device_id):
            # First contact: the display's configuration becomes the stored one.
            try:
                config = clean_config(hello.get("config") or {})
            except ConfigError as err:
                _LOGGER.warning("%s: configuration of the display not taken over: %s", self.name, err)
                config = clean_config({})
            self.store.adopt(self.device_id, config)
        config = self.store.config(self.device_id)
        rev = config_revision(config)
        if hello.get("rev") != rev:
            self._send({"type": "config", "rev": rev, "config": config})
            return  # the display stores it and says hello again

        self.last_error = None
        self._send({"type": "password", "password": self.store.password(self.device_id)})
        self._send({"type": "welcome", "ha_version": HA_VERSION, "proto": PROTOCOL})
        self._watch = watched_entities(config)
        states = {}
        for entity_id in self._watch:
            state = self.hass.states.get(entity_id)
            if state is None and entity_id not in self._warned:
                self._warned.add(entity_id)
                _LOGGER.warning("%s shows %s, which does not exist in HA", self.name, entity_id)
            states[entity_id] = self._payload(entity_id, state)
        if states:
            self._send({"type": "event", "event": {"a": states}})
            self._unsubs.append(async_track_state_change_event(self.hass, self._watch, self._on_state))
        self._set_connected(True)
        if config.get("weather"):
            # after connected: the task may run to its end right away (eager start)
            self._unsubs.append(async_track_time_interval(self.hass, self._forecast_tick, FORECAST_EVERY))
            self.entry.async_create_task(self.hass, self._refresh_forecast(config["weather"]))

    @callback
    def _rename(self, display_name: str) -> bool:
        """Sends the entry title as hostname if the display has another. Asks once per name."""
        target = hostname(self.entry.title)
        if not display_name or target == display_name:
            return False
        if self._name_requested != target:
            self._name_requested = target
            self._send({"type": "name", "name": target})
            return True
        self.name = display_name
        self.hass.config_entries.async_update_entry(self.entry, title=display_name)
        self.update_device()
        return False

    @callback
    def update_device(self) -> None:
        device = dr.async_get(self.hass).async_get_or_create(
            config_entry_id=self.entry.entry_id,
            identifiers={(DOMAIN, self.device_id)},
            connections={(dr.CONNECTION_NETWORK_MAC, dr.format_mac(self.device_id))},
            manufacturer="Adafruit / eigene Firmware",
            model="MatrixPortal S3, 192×64 LED",
            name=self.entry.title,
            sw_version=self.version,
            configuration_url=f"http://{self.host}/",
        )
        self.ha_device_id = device.id

    def _payload(self, entity_id: str, state: State | None) -> dict[str, Any]:
        config = self.store.config(self.device_id) if self.store.has(self.device_id) else {}
        extra = self._forecast if entity_id == config.get("weather") else None
        return state_payload(state, extra)

    @callback
    def _on_state(self, event: Event[EventStateChangedData]) -> None:
        entity_id = event.data["entity_id"]
        new_state = event.data["new_state"]
        self._send({"type": "event", "event": {"a": {entity_id: self._payload(entity_id, new_state)}}})
        config = self.store.config(self.device_id)
        if entity_id == config.get("weather") and time.monotonic() - self._forecast_at > FORECAST_MIN_GAP:
            self.entry.async_create_task(self.hass, self._refresh_forecast(entity_id))

    @callback
    def _forecast_tick(self, _now: Any) -> None:
        weather = self.store.config(self.device_id).get("weather")
        if weather:
            self.entry.async_create_task(self.hass, self._refresh_forecast(weather))

    async def _refresh_forecast(self, entity_id: str) -> None:
        """Today's min/max from weather.get_forecasts, sent as attributes of the weather state."""
        self._forecast_at = time.monotonic()
        try:
            response = await self.hass.services.async_call(
                "weather", "get_forecasts", {"entity_id": entity_id, "type": "daily"},
                blocking=True, return_response=True,
            )
            today = response[entity_id]["forecast"][0]
            forecast = {"forecast_high": today.get("temperature"), "forecast_low": today.get("templow")}
        except (HomeAssistantError, vol.Invalid, KeyError, IndexError, TypeError) as err:
            _LOGGER.debug("%s: no forecast for %s: %s", self.name, entity_id, err)
            return
        if forecast != self._forecast:
            self._forecast = forecast
            if self.connected:
                self._send({"type": "event", "event": {"a": {entity_id: self._payload(entity_id, self.hass.states.get(entity_id))}}})

    async def _on_get_calendar(self, data: dict[str, Any]) -> None:
        """Events of the requested calendars, each in its own message, then calendar_end."""
        if not self.connected:
            return
        request_id = data.get("id")
        allowed = config_calendars(self.store.config(self.device_id))
        all_ok = True
        requests = data.get("calendars") if isinstance(data.get("calendars"), list) else []
        for request in requests[:12]:
            if not isinstance(request, dict):
                continue
            entity_id = request.get("entity")
            events: list[dict[str, Any]] = []
            ok = False
            if entity_id not in allowed:
                _LOGGER.warning("%s: refused calendar %s, not in its configuration", self.name, entity_id)
            else:
                try:
                    response = await self.hass.services.async_call(
                        "calendar", "get_events",
                        {"entity_id": entity_id, "start_date_time": request.get("start"),
                         "end_date_time": request.get("end")},
                        blocking=True, return_response=True,
                    )
                    events = trim_events(response.get(entity_id, {}).get("events", []))
                    ok = True
                except (HomeAssistantError, vol.Invalid, ValueError, TypeError) as err:
                    _LOGGER.warning("%s: calendar %s failed: %s", self.name, entity_id, err)
            all_ok &= ok
            self._send({"type": "calendar", "id": request_id, "entity": entity_id, "ok": ok, "events": events})
        self._send({"type": "calendar_end", "id": request_id, "ok": all_ok})

    # ── To the display ──

    @callback
    def set(self, **values: Any) -> bool:
        """Runtime settings: on, brightness, demo, design, header, pac_every, strip_*, view, effect, saver*, doorbell_*."""
        if not self.connected:
            return False
        self._send({"type": "set", **values})
        self.status.update(values)  # optimistic, the display confirms with its status
        if values.get("brightness"):
            self.status["on"] = True
        if values.get("strip_brightness") or values.get("strip_rgb"):
            self.status["strip_on"] = values.get("strip_on", True)
        self._changed()
        return True

    @callback
    def command(self, name: str) -> bool:
        if not self.connected:
            return False
        self._send({"type": "command", "command": name})
        return True

    @callback
    def push_config(self) -> bool:
        """Sends the stored configuration if the display listens."""
        if self._ws is None or self.mode != "ha" or not self.store.has(self.device_id):
            return False
        config = self.store.config(self.device_id)
        self._send({"type": "config", "rev": config_revision(config), "config": config})
        return True

    @callback
    def push_name(self) -> None:
        """The entry title is the display's name; the display takes it as hostname and restarts."""
        self.name = self.entry.title
        self.update_device()
        if self.connected:
            self._name_requested = hostname(self.entry.title)
            self._send({"type": "name", "name": hostname(self.entry.title)})
