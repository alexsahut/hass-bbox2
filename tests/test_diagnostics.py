"""Tests for the bbox diagnostics."""

from unittest.mock import AsyncMock

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from custom_components.bbox.diagnostics import async_get_config_entry_diagnostics

DIAG_METHODS = (
    "device.async_get_bbox_summary",
    "device.async_get_bbox_info",
    "ddns.async_get_ddns",
    "iptv.async_get_iptv_info",
    "lan.async_get_connected_devices",
    "lan.async_get_device_infos",
    "lan.async_get_lan_stats",
    "parentalcontrol.async_get_parental_control_service_state",
    "services.async_get_bbox_services",
    "voip.async_get_voip_voicemail",
    "wifi.async_get_wireless",
    "wifi.async_get_stats_5",
    "wifi.async_get_stats_24",
    "wifi.async_get_wps",
    "wifi.async_get_repeater",
    "wan.async_get_wan_ip",
    "wan.async_get_wan_ftth",
    "wan.async_get_wan_ip_stats",
)


async def test_diagnostics(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    router,
) -> None:
    """Diagnostics expose entry, data and raw sections."""
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    # The diagnostics code reads ``func.__name__`` of each API method.
    bbox = router.return_value
    for path in DIAG_METHODS:
        *parents, name = path.split(".")
        api = bbox
        for part in parents:
            api = getattr(api, part)
        method = getattr(api, name)
        if not isinstance(method, AsyncMock):
            method = AsyncMock(return_value={})
            setattr(api, name, method)
        method.__name__ = name

    result = await async_get_config_entry_diagnostics(hass, config_entry)

    assert set(result) == {"entry", "data", "raw"}
    assert "async_get_bbox_info" in result["raw"]
    assert "async_get_wan_ip" in result["raw"]
