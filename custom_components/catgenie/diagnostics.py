"""Diagnostics: the raw cloud JSON, with secrets redacted."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .const import CONF_PHONE, CONF_REFRESH_TOKEN, CONF_SIGNING_SECRET

TO_REDACT = {
    CONF_PHONE,
    CONF_REFRESH_TOKEN,
    CONF_SIGNING_SECRET,
    "macAddress",
    "bleConnectionId",
    "serialNumber",
    "phone",
    "email",
    "certificate",
    "certificatePem",
    "privateKey",
    "token",
}


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry) -> dict[str, Any]:
    coordinator = entry.runtime_data
    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "options": dict(entry.options),
        "base_url": coordinator.client.base_url,
        "has_signing_secret": bool(coordinator.client.signing_secret),
        "devices": [async_redact_data(g.raw, TO_REDACT) for g in (coordinator.data or {}).values()],
    }
