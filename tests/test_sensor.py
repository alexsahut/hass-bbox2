"""Tests for the Bbox sensor platform."""

import pytest
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from custom_components.bbox.const import DOMAIN

from .common import setup_entry
from .conftest import FakeBox
from .const import SERIAL


async def test_sensors_state(
    hass: HomeAssistant, config_entry: ConfigEntry, router: FakeBox
) -> None:
    """Sensors read the values of the real 5696b answers."""
    await setup_entry(hass, config_entry)

    # wan/ip: wan.ip.address, wan.ip.ip6address.0.ipaddress
    assert hass.states.get("sensor.bbox_ip_address").state == "203.0.113.46"
    assert hass.states.get("sensor.bbox_ipv6_address").state == "2001:db8:8::8"
    # wan/ip/stats: rx.bytes = "1019469336801" (str), converted to kB
    assert float(hass.states.get("sensor.bbox_downloaded").state) == 1019469336.8
    assert float(hass.states.get("sensor.bbox_download_speed").state) == 25525.0
    # device/mem: free * 100 / total
    assert float(hass.states.get("sensor.bbox_memory_free").state) == pytest.approx(
        969572 * 100 / 1883000
    )
    # device: no temperature on the 5696b, device/cpu gives it in m°C
    assert float(hass.states.get("sensor.bbox_system_temperature").state) == 50.5
    assert hass.states.get("sensor.bbox_boot_counter").state == "14"


async def test_unique_ids_use_the_serial_number(
    hass: HomeAssistant, config_entry: ConfigEntry, router: FakeBox
) -> None:
    """The unique ids are unchanged: serial number of `device` + key (S5 reworks them)."""
    await setup_entry(hass, config_entry)
    registry = er.async_get(hass)
    entity = registry.async_get("sensor.bbox_ip_address")
    assert entity.unique_id == f"{SERIAL}-wan_ip.wan.ip.address"


async def test_public_mode_has_no_speedtest_sensor(
    hass: HomeAssistant, public_config_entry: ConfigEntry, public_router: FakeBox
) -> None:
    """Without password the sensor which needs speedtest/info is not created."""
    await setup_entry(hass, public_config_entry)

    registry = er.async_get(hass)
    unique_ids = {
        e.unique_id
        for e in er.async_entries_for_config_entry(
            registry, public_config_entry.entry_id
        )
    }
    assert not any("speedtest" in uid for uid in unique_ids)
    assert hass.states.get("sensor.bbox_ip_address").state == "203.0.113.46"
    # no password: the `device` answer has no serial number
    assert "ABC12345-wan_ip.wan.ip.address" in unique_ids


async def test_password_sensors_are_created_with_password(
    hass: HomeAssistant, config_entry: ConfigEntry, router: FakeBox
) -> None:
    """With a password the speedtest sensor exists (disabled by default)."""
    await setup_entry(hass, config_entry)
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(
        "sensor",
        DOMAIN,
        f"{SERIAL}-speedtest_infos.speedtest.latestmeasurements.download.0.speed",
    )
    assert entity_id is not None


async def test_password_removal_cleans_the_speedtest_sensor(
    hass: HomeAssistant, config_entry: ConfigEntry, router: FakeBox
) -> None:
    """Removing the password removes the entity which can not work anymore."""
    await setup_entry(hass, config_entry)
    registry = er.async_get(hass)
    unique_id = (
        f"{SERIAL}-speedtest_infos.speedtest.latestmeasurements.download.0.speed"
    )
    assert registry.async_get_entity_id("sensor", DOMAIN, unique_id)

    router.requests.clear()
    hass.config_entries.async_update_entry(
        config_entry, data={**config_entry.data, "password": ""}
    )
    await hass.async_block_till_done()

    assert config_entry.state == ConfigEntryState.LOADED
    assert registry.async_get_entity_id("sensor", DOMAIN, unique_id) is None
    assert "speedtest/info" not in router.endpoints
    assert ("POST", "login") not in router.requests


async def test_missing_values(
    hass: HomeAssistant, config_entry: ConfigEntry, router: FakeBox
) -> None:
    """A value missing in an answer gives an unknown state, not an error."""
    router.route("device/cpu", [{"device": {"cpu": {}}}])
    router.route("device/mem", [{"device": {"mem": {}}}])
    await setup_entry(hass, config_entry)

    assert hass.states.get("sensor.bbox_ip_address").state == "203.0.113.46"
    assert hass.states.get("sensor.bbox_system_temperature").state == STATE_UNKNOWN
    assert hass.states.get("sensor.bbox_memory_free").state == STATE_UNKNOWN


async def test_temperature_from_device_when_present(
    hass: HomeAssistant, config_entry: ConfigEntry, router: FakeBox
) -> None:
    """The temperature of `device` is used when the box gives it (°C)."""
    device = [{"device": {"temperature": {"current": 41}, "serialnumber": SERIAL}}]
    router.route("device", device)
    await setup_entry(hass, config_entry)
    assert float(hass.states.get("sensor.bbox_system_temperature").state) == 41


async def test_sensor_unavailable_without_its_endpoint(
    hass: HomeAssistant, config_entry: ConfigEntry, router: FakeBox
) -> None:
    """Only the sensors which depend on a failing endpoint are unavailable."""
    router.route("device/mem", status=500)
    await setup_entry(hass, config_entry)

    assert hass.states.get("sensor.bbox_memory_free").state == STATE_UNAVAILABLE
    assert hass.states.get("sensor.bbox_ip_address").state == "203.0.113.46"
    assert float(hass.states.get("sensor.bbox_downloaded").state) > 0
