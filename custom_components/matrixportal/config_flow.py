"""Adding displays: found by mDNS, or by address."""

from __future__ import annotations

import logging
import secrets
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import ConfigEntryState, ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

from .const import CONF_LINK_KEY, CONF_PAIR_PASSWORD, DOMAIN
from .link import async_read_hello, async_verify_key

_LOGGER = logging.getLogger(__name__)


class MatrixPortalConfigFlow(ConfigFlow, domain=DOMAIN):
    """One config entry per display, identified by its MAC."""

    VERSION = 1

    def __init__(self) -> None:
        self._host = ""
        self._name = ""
        self._paired = False
        self._protected = False
        # One key per flow: a retry uses the key the display may already have.
        self._key = secrets.token_hex(32)

    async def async_step_zeroconf(self, discovery_info: ZeroconfServiceInfo) -> ConfigFlowResult:
        device_id = discovery_info.properties.get("id")
        if not device_id:
            return self.async_abort(reason="not_matrixportal")
        self._host = discovery_info.host
        self._name = discovery_info.properties.get("name") or discovery_info.hostname.split(".")[0]
        self._paired = discovery_info.properties.get("paired") == "1"
        await self.async_set_unique_id(device_id)
        entry = self.hass.config_entries.async_entry_for_domain_unique_id(DOMAIN, device_id)
        if entry is not None and entry.state is ConfigEntryState.LOADED:
            entry.runtime_data.wake()  # (re)started: let its connection retry now
        self._abort_if_unique_id_configured(updates={CONF_HOST: self._host})
        self.context["title_placeholders"] = {"name": self._name}
        if self._paired:
            return self.async_abort(reason="paired_elsewhere")
        try:
            self._protected = bool((await async_read_hello(self.hass, self._host)).get("protected"))
        except (aiohttp.ClientError, TimeoutError, OSError, ValueError):
            return self.async_abort(reason="cannot_connect")
        return await self.async_step_confirm()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            try:
                hello = await async_read_hello(self.hass, host)
            except (aiohttp.ClientError, TimeoutError, OSError, ValueError):
                errors["base"] = "cannot_connect"
            else:
                self._host = host
                self._name = hello.get("name") or host
                self._paired = bool(hello.get("paired"))
                self._protected = bool(hello.get("protected"))
                await self.async_set_unique_id(hello["id"])
                self._abort_if_unique_id_configured(updates={CONF_HOST: host})
                if self._paired:
                    return self.async_abort(reason="paired_elsewhere")
                return await self.async_step_confirm()
        return self.async_show_form(
            step_id="user", data_schema=vol.Schema({vol.Required(CONF_HOST): str}), errors=errors
        )

    async def async_step_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                hello = await async_read_hello(self.hass, self._host)
                if hello.get("paired") and not await async_verify_key(self.hass, self._host, self._key):
                    return self.async_abort(reason="paired_elsewhere")
            except (aiohttp.ClientError, TimeoutError, OSError, ValueError):
                errors["base"] = "cannot_connect"
            else:
                # The connection pairs the display with the key of the entry.
                return self.async_create_entry(
                    title=self._name,
                    data={
                        CONF_HOST: self._host,
                        CONF_LINK_KEY: self._key,
                        CONF_PAIR_PASSWORD: user_input.get(CONF_PAIR_PASSWORD, ""),
                    },
                )
        schema = vol.Schema({vol.Required(CONF_PAIR_PASSWORD): str} if self._protected else {})
        return self.async_show_form(
            step_id="confirm",
            data_schema=schema,
            description_placeholders={"name": self._name, "host": self._host},
            errors=errors,
        )
