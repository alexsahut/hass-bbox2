"""Tests of the coordinator: tolerance by endpoint, reconnection."""

import logging

import aiohttp
import pytest
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant

from custom_components.bbox.coordinator import (
    AUTHENTICATED_ENDPOINTS,
    PUBLIC_ENDPOINTS,
    _normalize,
)

from .common import setup_entry
from .conftest import FakeBox
from .const import AUTHENTICATED_ANSWERS, PUBLIC_ANSWERS


async def refresh(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()


async def test_data_keys(
    hass: HomeAssistant, config_entry: ConfigEntry, router: FakeBox
) -> None:
    """The data holds one entry per endpoint, in the shape the entities use."""
    await setup_entry(hass, config_entry)
    data = config_entry.runtime_data.data
    assert set(data) == {e.key for e in PUBLIC_ENDPOINTS + AUTHENTICATED_ENDPOINTS}
    assert data["info"]["device"]["modelname"] == "F@st5696b"
    assert "hosts" in data["devices"]


async def test_one_failing_endpoint_only_affects_its_entities(
    hass: HomeAssistant, config_entry: ConfigEntry, router: FakeBox
) -> None:
    """404, timeout, invalid JSON: each one only hides the entities depending on it."""
    router.route("device/mem", status=404)
    router.route("device/led", exc=TimeoutError())
    router.route("wan/ip", text="<html>not json</html>")
    await setup_entry(hass, config_entry)

    assert config_entry.state == ConfigEntryState.LOADED
    assert hass.states.get("sensor.bbox_memory_free").state == STATE_UNAVAILABLE
    assert hass.states.get("sensor.bbox_ip_address").state == STATE_UNAVAILABLE
    assert hass.states.get("sensor.bbox_ipv6_address").state == STATE_UNAVAILABLE
    # the other entities keep their values
    assert float(hass.states.get("sensor.bbox_downloaded").state) > 0
    assert float(hass.states.get("sensor.bbox_system_temperature").state) == 50.5
    # the link status now comes from wan/ip
    assert hass.states.get("binary_sensor.bbox_link_status").state == STATE_UNAVAILABLE
    assert hass.states.get("button.bbox_refresh").state != STATE_UNAVAILABLE


async def test_authenticated_endpoint_failure_keeps_public_entities(
    hass: HomeAssistant, config_entry: ConfigEntry, router: FakeBox
) -> None:
    """If hosts and speedtest fail, the public sensors are not affected."""
    router.route("hosts", status=500)
    router.route("speedtest/info", exc=aiohttp.ClientError())
    await setup_entry(hass, config_entry)

    assert hass.states.get("sensor.bbox_ip_address").state == "203.0.113.46"
    assert config_entry.runtime_data.last_update_success
    assert "devices" not in config_entry.runtime_data.data


async def test_endpoint_recovers(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    router: FakeBox,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An endpoint in error is logged once, and its entities recover with it."""
    caplog.set_level(logging.INFO)
    router.route("device/mem", status=500)
    await setup_entry(hass, config_entry)
    assert hass.states.get("sensor.bbox_memory_free").state == STATE_UNAVAILABLE

    await refresh(hass, config_entry)  # still failing: no new warning
    assert caplog.text.count("Unable to read device/mem") == 1

    router.route("device/mem", PUBLIC_ANSWERS["device/mem"])
    await refresh(hass, config_entry)

    assert float(hass.states.get("sensor.bbox_memory_free").state) > 50
    assert "device/mem is available again" in caplog.text


async def test_missing_endpoint_is_not_requested_again(
    hass: HomeAssistant, config_entry: ConfigEntry, router: FakeBox
) -> None:
    """A 404 means the box has not this endpoint: asked once, never again."""
    router.route("speedtest/info", status=404)
    await setup_entry(hass, config_entry)
    await refresh(hass, config_entry)
    await refresh(hass, config_entry)

    assert router.count("speedtest/info") == 1
    assert router.count("device/mem") == 3
    assert hass.states.get("sensor.bbox_ip_address").state == "203.0.113.46"


async def test_all_endpoints_failing_fails_the_update(
    hass: HomeAssistant, config_entry: ConfigEntry, router: FakeBox
) -> None:
    """UpdateFailed only when no endpoint answered."""
    for endpoint in list(PUBLIC_ANSWERS) + list(AUTHENTICATED_ANSWERS):
        router.route(endpoint, exc=aiohttp.ClientError("down"))
    await setup_entry(hass, config_entry)

    assert config_entry.state == ConfigEntryState.SETUP_RETRY


async def test_unreachable_after_setup_makes_entities_unavailable(
    hass: HomeAssistant, config_entry: ConfigEntry, router: FakeBox
) -> None:
    """If the whole box stops answering, every entity is unavailable."""
    await setup_entry(hass, config_entry)
    for endpoint in list(PUBLIC_ANSWERS) + list(AUTHENTICATED_ANSWERS):
        router.route(endpoint, exc=aiohttp.ClientError("down"))
    await refresh(hass, config_entry)

    assert not config_entry.runtime_data.last_update_success
    assert hass.states.get("sensor.bbox_ip_address").state == STATE_UNAVAILABLE
    assert hass.states.get("button.bbox_refresh").state == STATE_UNAVAILABLE


async def test_no_endpoint_left(
    hass: HomeAssistant, public_config_entry: ConfigEntry, public_router: FakeBox
) -> None:
    """When all the endpoints are missing (404), the update fails."""
    for endpoint in PUBLIC_ANSWERS:
        public_router.route(endpoint, status=404)
    await setup_entry(hass, public_config_entry)
    assert public_config_entry.state == ConfigEntryState.SETUP_RETRY


async def test_session_expired_at_refresh(
    hass: HomeAssistant, config_entry: ConfigEntry, router: FakeBox
) -> None:
    """401 on an authenticated endpoint: new login, one new attempt, success."""
    await setup_entry(hass, config_entry)
    assert router.count("login", "POST") == 1

    router.route(
        "hosts",
        status=401,
        then=[{"status": 200, "json": AUTHENTICATED_ANSWERS["hosts"]}],
    )
    await refresh(hass, config_entry)

    assert config_entry.runtime_data.last_update_success
    assert "devices" in config_entry.runtime_data.data
    assert router.count("login", "POST") == 2
    assert not hass.config_entries.flow.async_progress()


async def test_login_refused_at_refresh_starts_reauth(
    hass: HomeAssistant, config_entry: ConfigEntry, router: FakeBox
) -> None:
    """401, then the login is refused: ConfigEntryAuthFailed, reauth flow."""
    await setup_entry(hass, config_entry)
    router.route("device", status=401)
    router.route("login", status=401, method="POST")

    await refresh(hass, config_entry)
    await hass.async_block_till_done()

    flows = hass.config_entries.flow.async_progress()
    assert [f["context"]["source"] for f in flows] == ["reauth"]
    assert router.count("login", "POST") == 2


async def test_wrong_password_at_setup_starts_reauth(
    hass: HomeAssistant, config_entry: ConfigEntry, router: FakeBox
) -> None:
    """A refused login at setup: setup error and reauth, without retry storm."""
    router.route("login", status=401, method="POST")
    await setup_entry(hass, config_entry)

    assert config_entry.state == ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress()
    assert [f["context"]["source"] for f in flows] == ["reauth"]
    assert router.count("login", "POST") == 1  # not repeated by each endpoint


async def test_no_password_no_authenticated_call(
    hass: HomeAssistant, public_config_entry: ConfigEntry, public_router: FakeBox
) -> None:
    """Without password no authenticated endpoint is requested, ever."""
    await setup_entry(hass, public_config_entry)
    await refresh(hass, public_config_entry)

    forbidden = {e.path for e in AUTHENTICATED_ENDPOINTS}
    assert not public_router.endpoints & forbidden
    assert ("POST", "login") not in public_router.requests
    assert set(public_config_entry.runtime_data.data) == {
        e.key for e in PUBLIC_ENDPOINTS
    }


def test_normalize() -> None:
    """The answers are lists of one element; the hosts may come in several parts."""
    assert _normalize("x", {"a": 1}) == {"a": 1}
    assert _normalize("x", [{"a": 1}]) == {"a": 1}
    hosts = _normalize(
        "devices",
        [{"hosts": {"list": [{"id": 1}]}}, {"hosts": {"list": [{"id": 2}]}}],
    )
    assert hosts == {"hosts": {"list": [{"id": 1}, {"id": 2}]}}
    for payload in ([], [1], "text", [{"a": 1}, {"b": 2}]):
        with pytest.raises(Exception, match="Unexpected content"):
            _normalize("x", payload)
