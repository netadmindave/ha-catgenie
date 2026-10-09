"""The CatGenie integration (cloud)."""

from __future__ import annotations

import logging
from datetime import time

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import dt as dt_util

from .api import CatGenieAuthError, CatGenieClient
from .const import (
    CONF_BASE_URL,
    CONF_REFRESH_TOKEN,
    CONF_SIGNING_SECRET,
    DOMAIN,
    MAX_SCHEDULE_ENTRIES,
    PLATFORMS,
)
from .coordinator import CatGenieCoordinator, persist_credentials
from .models import local_hm_to_utc

_LOGGER = logging.getLogger(__name__)

type CatGenieConfigEntry = ConfigEntry[CatGenieCoordinator]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

ATTR_DEVICE_ID = "device_id"
SERVICE_SET_SCHEDULE = "set_schedule"
SERVICE_SET_DND = "set_do_not_disturb"
SERVICE_SET_CONFIGURATION = "set_configuration"


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    _register_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: CatGenieConfigEntry) -> bool:
    client = CatGenieClient(
        async_get_clientsession(hass),
        refresh_token=entry.data.get(CONF_REFRESH_TOKEN),
        signing_secret=entry.data.get(CONF_SIGNING_SECRET),
        base_url=entry.data.get(CONF_BASE_URL),
    )
    client._on_credentials_changed = lambda: hass.loop.call_soon(
        persist_credentials, hass, entry, client
    )

    try:
        await client.refresh_access_token()
    except CatGenieAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err

    coordinator = CatGenieCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: CatGenieConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload(hass: HomeAssistant, entry: CatGenieConfigEntry) -> None:
    # Only reload on option changes, not when tokens are rotated into entry.data.
    coordinator = getattr(entry, "runtime_data", None)
    if coordinator is None or dict(entry.options) != coordinator.options_snapshot:
        await hass.config_entries.async_reload(entry.entry_id)


# ---------------------------------------------------------------- services


def _resolve(hass: HomeAssistant, device_id: str) -> tuple[CatGenieCoordinator, str]:
    dev = dr.async_get(hass).async_get(device_id)
    if dev is None:
        raise HomeAssistantError(f"Unknown device {device_id}")
    for domain, ident in dev.identifiers:
        if domain != DOMAIN:
            continue
        for entry_id in dev.config_entries:
            entry = hass.config_entries.async_get_entry(entry_id)
            coordinator = getattr(entry, "runtime_data", None) if entry else None
            if entry and entry.domain == DOMAIN and coordinator and ident in (coordinator.data or {}):
                return coordinator, ident
    raise HomeAssistantError("Device is not a loaded CatGenie")


def _register_services(hass: HomeAssistant) -> None:
    async def set_schedule(call: ServiceCall) -> None:
        coordinator, mid = _resolve(hass, call.data[ATTR_DEVICE_ID])
        tz = dt_util.get_default_time_zone()
        times: list[time] = call.data["times"]
        cfg = coordinator.data[mid].configuration
        cfg["schedule"] = sorted(local_hm_to_utc(t, tz) for t in times)
        if call.data["activate"]:
            cfg.update(mode=1, manual=0)
        await coordinator.async_set_configuration(mid, cfg)

    async def set_dnd(call: ServiceCall) -> None:
        coordinator, mid = _resolve(hass, call.data[ATTR_DEVICE_ID])
        tz = dt_util.get_default_time_zone()
        cfg = coordinator.data[mid].configuration
        cfg["dndFrom"] = local_hm_to_utc(call.data["start"], tz)
        cfg["dndTo"] = local_hm_to_utc(call.data["end"], tz)
        await coordinator.async_set_configuration(mid, cfg)

    async def set_configuration(call: ServiceCall) -> None:
        coordinator, mid = _resolve(hass, call.data[ATTR_DEVICE_ID])
        cfg = coordinator.data[mid].configuration
        cfg.update(call.data["configuration"])
        await coordinator.async_set_configuration(mid, cfg)

    device_schema = {vol.Required(ATTR_DEVICE_ID): cv.string}
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_SCHEDULE,
        set_schedule,
        vol.Schema(
            {
                **device_schema,
                vol.Required("times"): vol.All(
                    cv.ensure_list, [cv.time], vol.Length(min=0, max=MAX_SCHEDULE_ENTRIES)
                ),
                vol.Optional("activate", default=True): cv.boolean,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_DND,
        set_dnd,
        vol.Schema({**device_schema, vol.Required("start"): cv.time, vol.Required("end"): cv.time}),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_CONFIGURATION,
        set_configuration,
        vol.Schema({**device_schema, vol.Required("configuration"): dict}),
    )
