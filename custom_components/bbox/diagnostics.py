"""Diagnostics support."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .api import BboxError
from .const import TO_REDACT

# Extra endpoints read (GET) for the diagnostics only.
PUBLIC_DIAGNOSTIC_ENDPOINTS = (
    "hosts/me",
    "lan/stats",
    "services",
    "wan/ftth/stats",
    "voip/voicemail",
)
AUTHENTICATED_DIAGNOSTIC_ENDPOINTS = (
    "dyndns",
    "iptv",
    "wireless/24/stats",
    "wireless/5/stats",
    "wireless/repeater",
)


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data

    raw: dict[str, Any] = {}
    endpoints = [(path, False) for path in PUBLIC_DIAGNOSTIC_ENDPOINTS]
    if coordinator.has_password:
        endpoints += [(path, True) for path in AUTHENTICATED_DIAGNOSTIC_ENDPOINTS]
    for path, authenticated in endpoints:
        try:
            raw[path] = await coordinator.client.async_get(
                path, authenticated=authenticated
            )
        except BboxError as error:
            raw[path] = {"error": f"{type(error).__name__}: {error}"}

    return {
        "entry": {
            "data": async_redact_data(entry.data, TO_REDACT),
            "options": async_redact_data(entry.options, TO_REDACT),
        },
        "data": async_redact_data(coordinator.data, TO_REDACT),
        "raw": async_redact_data(raw, TO_REDACT),
    }
