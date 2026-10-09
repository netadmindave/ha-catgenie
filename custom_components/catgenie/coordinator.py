"""Polling coordinator for CatGenie devices."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import CatGenieApiError, CatGenieAuthError, CatGenieClient, CatGenieError
from .const import (
    CONF_BASE_URL,
    CONF_REFRESH_TOKEN,
    CONF_SCAN_INTERVAL,
    CONF_SIGNING_SECRET,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    FAST_SCAN_INTERVAL,
)
from .models import CatGenie

_LOGGER = logging.getLogger(__name__)


class CatGenieCoordinator(DataUpdateCoordinator[dict[str, CatGenie]]):
    """Fetch all CatGenies on the account."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: CatGenieClient) -> None:
        self._normal_interval = timedelta(
            seconds=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        )
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=self._normal_interval,
        )
        self.client = client
        self.options_snapshot: dict[str, Any] = dict(entry.options)

    async def _async_update_data(self) -> dict[str, CatGenie]:
        try:
            things = await self.client.get_devices()
        except CatGenieAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except (CatGenieError, aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise UpdateFailed(str(err)) from err

        devices = {CatGenie(t).manufacturer_id: CatGenie(t) for t in things}
        # Poll faster while a cycle is running so progress looks live.
        busy = any(d.is_cleaning for d in devices.values())
        self.update_interval = (
            timedelta(seconds=min(FAST_SCAN_INTERVAL, self._normal_interval.total_seconds()))
            if busy
            else self._normal_interval
        )
        return devices

    # ----------------------------------------------------------- commands
    async def async_operation(self, manufacturer_id: str, state: int) -> None:
        await self._call(self.client.set_operation(manufacturer_id, state))

    async def async_set_configuration(self, manufacturer_id: str, configuration: dict[str, Any]) -> None:
        await self._call(self.client.set_configuration(manufacturer_id, configuration))

    async def _call(self, coro) -> None:
        try:
            await coro
        except CatGenieAuthError as err:
            self.config_entry.async_start_reauth(self.hass)
            raise HomeAssistantError(f"CatGenie authentication failed: {err}") from err
        except (CatGenieApiError, CatGenieError, aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise HomeAssistantError(f"CatGenie request failed: {err}") from err
        # The cloud relays to the unit over MQTT; give it a moment to report back.
        await asyncio.sleep(2)
        await self.async_request_refresh()


def persist_credentials(hass: HomeAssistant, entry: ConfigEntry, client: CatGenieClient) -> None:
    """Save rotated tokens / signing secret back into the config entry."""
    data = {
        **entry.data,
        CONF_REFRESH_TOKEN: client.refresh_token,
        CONF_SIGNING_SECRET: client.signing_secret,
        CONF_BASE_URL: client.base_url,
    }
    if data != dict(entry.data):
        hass.config_entries.async_update_entry(entry, data=data)
