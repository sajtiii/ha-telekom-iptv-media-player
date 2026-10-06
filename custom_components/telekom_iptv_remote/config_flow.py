"""Config flow for the Telekom IPTV Box Media Player integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_HOST, CONF_NAME
from homeassistant.core import callback
from telekom_iptv_remote import PairingError, Remote

from .const import (
    CONF_CID,
    CONF_CODE,
    CONF_KEY,
    CONF_SCAN_INTERVAL,
    CONF_VOLUME_MAX,
    CONF_VOLUME_MIN,
    DEFAULT_CLIENT_NAME,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_VOLUME_MAX,
    DEFAULT_VOLUME_MIN,
    DOMAIN,
)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_CODE): str,  # 8-hex code shown on the TV
        vol.Optional(CONF_NAME, default=DEFAULT_CLIENT_NAME): str,  # name shown to the box
    }
)


class TelekomConfigFlow(ConfigFlow, domain=DOMAIN):
    """Pair with the box and create the entry."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Pair using the IP and the 8-hex code on the TV screen."""
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            code = user_input[CONF_CODE].strip()
            name = user_input.get(CONF_NAME, DEFAULT_CLIENT_NAME).strip()
            try:
                remote = await self.hass.async_add_executor_job(Remote.pair, host, code, name)
            except PairingError:
                errors["base"] = "pair_failed"
            except ValueError:
                errors["base"] = "invalid_code"
            except Exception:  # noqa: BLE001
                errors["base"] = "cannot_connect"
            else:
                dev = remote.device
                await self.async_set_unique_id(dev.cid)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=name or f"Telekom IPTV Box Media Player ({host})",
                    data={
                        CONF_HOST: host,
                        CONF_CID: dev.cid,
                        CONF_KEY: dev.key,
                        CONF_NAME: name,
                    },
                )

        return self.async_show_form(step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return TelekomOptionsFlow()


class TelekomOptionsFlow(OptionsFlow):
    """Tune the volume range and poll interval."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        opts = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_VOLUME_MIN,
                    default=opts.get(CONF_VOLUME_MIN, DEFAULT_VOLUME_MIN),
                ): vol.All(int, vol.Range(min=0, max=100)),
                vol.Required(
                    CONF_VOLUME_MAX,
                    default=opts.get(CONF_VOLUME_MAX, DEFAULT_VOLUME_MAX),
                ): vol.All(int, vol.Range(min=1, max=100)),
                vol.Required(
                    CONF_SCAN_INTERVAL,
                    default=opts.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                ): vol.All(int, vol.Range(min=2, max=300)),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
