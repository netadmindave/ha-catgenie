"""Config flow: phone number -> SMS code, same as the app."""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import CatGenieApiError, CatGenieAuthError, CatGenieClient, CatGenieError
from .const import (
    CONF_BASE_URL,
    CONF_COUNTRY_CODE,
    CONF_PHONE,
    CONF_REFRESH_TOKEN,
    CONF_SCAN_INTERVAL,
    CONF_SIGNING_SECRET,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


def to_e164(country_code: str, phone: str) -> str:
    """'+' + country code + national number without leading zeros (app logic)."""
    cc = re.sub(r"\D", "", str(country_code))
    num = re.sub(r"\D", "", str(phone)).lstrip("0")
    if num.startswith(cc) and len(num) > 10:  # user typed the full number
        num = num[len(cc) :]
    return f"+{cc}{num}"


def _api_message(err: Exception) -> str:
    if isinstance(err, CatGenieApiError) and isinstance(err.body, dict):
        return str(err.body.get("message") or err.body.get("code") or err)
    return str(err)


class CatGenieConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._client: CatGenieClient | None = None
        self._phone: str | None = None
        self._country: str = "1"

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        placeholders = {"detail": ""}
        if user_input is not None:
            self._country = user_input[CONF_COUNTRY_CODE]
            self._phone = to_e164(self._country, user_input[CONF_PHONE])
            self._client = CatGenieClient(async_get_clientsession(self.hass))
            try:
                await self._client.discover_base_url()
                await self._client.request_login_code(self._phone)
            except (aiohttp.ClientError, TimeoutError):
                errors["base"] = "cannot_connect"
            except CatGenieError as err:
                _LOGGER.warning("Requesting login code failed: %s", err)
                errors["base"] = "code_request_failed"
                placeholders["detail"] = _api_message(err)
            else:
                return await self.async_step_code()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_COUNTRY_CODE, default=self._country): str,
                    vol.Required(
                        CONF_PHONE, default=(self._phone or "").removeprefix(f"+{self._country}")
                    ): str,
                }
            ),
            errors=errors,
            description_placeholders=placeholders,
        )

    async def async_step_code(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        placeholders = {"phone": self._phone or "", "detail": ""}
        if user_input is not None and self._client and self._phone:
            try:
                await self._client.login_with_code(self._phone, user_input["code"])
            except (aiohttp.ClientError, TimeoutError):
                errors["base"] = "cannot_connect"
            except (CatGenieAuthError, CatGenieError) as err:
                _LOGGER.warning("Login failed: %s", err)
                errors["base"] = "invalid_code"
                placeholders["detail"] = _api_message(err)
            else:
                data = {
                    CONF_PHONE: self._phone,
                    CONF_COUNTRY_CODE: self._country,
                    CONF_BASE_URL: self._client.base_url,
                    CONF_REFRESH_TOKEN: self._client.refresh_token,
                    CONF_SIGNING_SECRET: self._client.signing_secret,
                }
                await self.async_set_unique_id(self._phone)
                if self.source == "reauth":
                    self._abort_if_unique_id_mismatch(reason="wrong_account")
                    return self.async_update_reload_and_abort(
                        self._get_reauth_entry(), data_updates=data
                    )
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=f"CatGenie ({self._phone})", data=data)

        return self.async_show_form(
            step_id="code",
            data_schema=vol.Schema({vol.Required("code"): str}),
            errors=errors,
            description_placeholders=placeholders,
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        self._country = entry_data.get(CONF_COUNTRY_CODE, "1")
        self._phone = entry_data.get(CONF_PHONE)
        return await self.async_step_user()

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return CatGenieOptionsFlow()


class CatGenieOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        opts = self.config_entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SCAN_INTERVAL,
                        default=opts.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                    ): vol.All(vol.Coerce(int), vol.Range(min=10, max=600)),
                }
            ),
        )
