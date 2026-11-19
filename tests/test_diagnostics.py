"""Tests for the bbox diagnostics."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from custom_components.bbox.diagnostics import (
    AUTHENTICATED_DIAGNOSTIC_ENDPOINTS,
    PUBLIC_DIAGNOSTIC_ENDPOINTS,
    async_get_config_entry_diagnostics,
)

from .common import setup_entry
from .conftest import FakeBox


async def test_diagnostics_with_password(
    hass: HomeAssistant, config_entry: ConfigEntry, router: FakeBox
) -> None:
    """Diagnostics read the extra endpoints (GET) and redact personal data."""
    for endpoint in PUBLIC_DIAGNOSTIC_ENDPOINTS + AUTHENTICATED_DIAGNOSTIC_ENDPOINTS:
        router.route(endpoint, [{"address": "203.0.113.1", "value": 1}])
    router.route("voip/voicemail", status=404)
    await setup_entry(hass, config_entry)

    result = await async_get_config_entry_diagnostics(hass, config_entry)

    assert set(result) == {"entry", "data", "raw"}
    assert result["entry"]["data"]["password"] == "**REDACTED**"
    assert result["data"]["info"]["device"]["serialnumber"] == "**REDACTED**"
    assert result["data"]["wan_ip"]["wan"]["ip"]["address"] == "**REDACTED**"
    assert set(result["raw"]) == set(
        PUBLIC_DIAGNOSTIC_ENDPOINTS + AUTHENTICATED_DIAGNOSTIC_ENDPOINTS
    )
    assert result["raw"]["services"][0]["value"] == 1
    assert result["raw"]["services"][0]["address"] == "**REDACTED**"
    assert "BboxNotFoundError" in result["raw"]["voip/voicemail"]["error"]


async def test_diagnostics_without_password(
    hass: HomeAssistant, public_config_entry: ConfigEntry, public_router: FakeBox
) -> None:
    """Without password, the authenticated endpoints are not requested."""
    for endpoint in PUBLIC_DIAGNOSTIC_ENDPOINTS:
        public_router.route(endpoint, [{}])
    await setup_entry(hass, public_config_entry)

    result = await async_get_config_entry_diagnostics(hass, public_config_entry)

    assert set(result["raw"]) == set(PUBLIC_DIAGNOSTIC_ENDPOINTS)
    assert not public_router.endpoints & set(AUTHENTICATED_DIAGNOSTIC_ENDPOINTS)


async def test_diagnostics_redact_ssid_and_token(
    hass: HomeAssistant, config_entry: ConfigEntry, router: FakeBox
) -> None:
    """A Wi-Fi SSID and a session token never appear in clear text."""
    secret_ssid = "MaBox-Secret-SSID"
    secret_token = "0123456789abcdef-secret-token"
    for endpoint in PUBLIC_DIAGNOSTIC_ENDPOINTS + AUTHENTICATED_DIAGNOSTIC_ENDPOINTS:
        router.route(
            endpoint,
            [
                {
                    "ssid": secret_ssid,
                    "device": {"token": secret_token},
                    "btoken": secret_token,
                    "nat": {"rules": [{"description": "rule", "externalip": "x"}]},
                }
            ],
        )
    await setup_entry(hass, config_entry)

    result = await async_get_config_entry_diagnostics(hass, config_entry)

    dump = repr(result)
    assert secret_ssid not in dump
    assert secret_token not in dump
    assert result["raw"]["services"][0]["ssid"] == "**REDACTED**"
    assert result["raw"]["services"][0]["device"]["token"] == "**REDACTED**"
