"""Tests for the Bbox sensor platform."""

import copy
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from custom_components.bbox.const import DOMAIN

from .common import setup_entry
from .conftest import FakeBox
from .const import BOX_ID, DEVICE_WITH_SERIAL, PUBLIC_ANSWERS, SERIAL


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


async def test_unique_ids_use_the_lan_mac_address(
    hass: HomeAssistant, config_entry: ConfigEntry, router: FakeBox
) -> None:
    """The unique ids are the LAN MAC address of the box + key."""
    await setup_entry(hass, config_entry)
    registry = er.async_get(hass)
    entity = registry.async_get("sensor.bbox_ip_address")
    assert entity.unique_id == f"{BOX_ID}-wan_ip.wan.ip.address"


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
    # no password: the `device` answer has no serial number, same unique ids
    assert f"{BOX_ID}-wan_ip.wan.ip.address" in unique_ids


async def test_password_sensors_are_created_with_password(
    hass: HomeAssistant, config_entry: ConfigEntry, router: FakeBox
) -> None:
    """With a password the speedtest sensor exists (disabled by default)."""
    await setup_entry(hass, config_entry)
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(
        "sensor",
        DOMAIN,
        f"{BOX_ID}-speedtest_infos.speedtest.latestmeasurements.download.0.speed",
    )
    assert entity_id is not None


async def test_password_removal_cleans_the_speedtest_sensor(
    hass: HomeAssistant, config_entry: ConfigEntry, router: FakeBox
) -> None:
    """Removing the password removes the entity which can not work anymore."""
    await setup_entry(hass, config_entry)
    registry = er.async_get(hass)
    unique_id = (
        f"{BOX_ID}-speedtest_infos.speedtest.latestmeasurements.download.0.speed"
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


def _entry(hass, config_entry, entity_id):
    return er.async_get(hass).async_get(entity_id)


def _enable(hass, config_entry, *entity_ids):
    registry = er.async_get(hass)
    for entity_id in entity_ids:
        registry.async_update_entity(entity_id, disabled_by=None)


# --- a) uptime -> start time -------------------------------------------------

BOOT = datetime(2026, 11, 19, 21, 4, 10, tzinfo=UTC) - timedelta(seconds=7560048)


async def test_boot_time_replaces_uptime(
    hass: HomeAssistant, config_entry: ConfigEntry, router: FakeBox
) -> None:
    """The start time = device.now - device.uptime, a TIMESTAMP without state class."""
    registry = er.async_get(hass)
    # an entity of the former Uptime sensor is left in the registry
    registry.async_get_or_create(
        "sensor", DOMAIN, f"{BOX_ID}-info.device.uptime", config_entry=config_entry
    )
    await setup_entry(hass, config_entry)

    state = hass.states.get("sensor.bbox_last_boot")
    assert datetime.fromisoformat(state.state) == BOOT
    assert state.attributes["device_class"] == SensorDeviceClass.TIMESTAMP
    assert "state_class" not in state.attributes
    assert registry.async_get("sensor.bbox_last_boot").unique_id == (
        f"{BOX_ID}-info.device.boot_time"
    )
    # the former sensor is removed
    assert (
        registry.async_get_entity_id("sensor", DOMAIN, f"{BOX_ID}-info.device.uptime")
        is None
    )
    assert hass.states.get("sensor.bbox_uptime") is None


async def test_boot_time_is_stable_between_updates(
    hass: HomeAssistant, config_entry: ConfigEntry, router: FakeBox
) -> None:
    """A jitter of a few seconds does not change the state; a reboot does."""
    await setup_entry(hass, config_entry)
    first = hass.states.get("sensor.bbox_last_boot")
    coordinator = config_entry.runtime_data

    async def refresh(now: str, uptime: int):
        device = copy.deepcopy(DEVICE_WITH_SERIAL)
        device[0]["device"]["now"] = now
        device[0]["device"]["uptime"] = uptime
        router.route("device", device)
        await coordinator.async_refresh()
        await hass.async_block_till_done()
        return hass.states.get("sensor.bbox_last_boot")

    # normal cycle 60 s later, then rounding jitter of +/- 2 s
    for now, uptime in (
        ("2026-11-19T22:05:10+0100", 7560108),
        ("2026-11-19T22:06:10+0100", 7560167),
        ("2026-11-19T22:07:10+0100", 7560230),
    ):
        state = await refresh(now, uptime)
        assert state.state == first.state
        assert state.last_updated == first.last_updated

    # reboot: the start time moves
    state = await refresh("2026-11-19T22:10:10+0100", 120)
    assert datetime.fromisoformat(state.state) == datetime(
        2026, 11, 19, 21, 8, 10, tzinfo=UTC
    )


async def test_boot_time_unknown_without_data(
    hass: HomeAssistant, config_entry: ConfigEntry, router: FakeBox
) -> None:
    """No `now`, or no uptime, or a naive date: unknown state."""
    for patch in ({"now": None}, {"uptime": None}, {"now": "2026-11-19T22:04:10"}):
        device = copy.deepcopy(DEVICE_WITH_SERIAL)
        device[0]["device"].update(patch)
        router.route("device", device)
        await hass.config_entries.async_reload(config_entry.entry_id) if (
            config_entry.state == ConfigEntryState.LOADED
        ) else await setup_entry(hass, config_entry)
        await hass.async_block_till_done()
        assert hass.states.get("sensor.bbox_last_boot").state == STATE_UNKNOWN


# --- b) occupation -----------------------------------------------------------


async def test_occupation_percent_and_raw(
    hass: HomeAssistant, config_entry: ConfigEntry, router: FakeBox
) -> None:
    """Percentage of the contractual bandwidth, and the raw field (disabled)."""
    registry = er.async_get(hass)
    await setup_entry(hass, config_entry)

    # fixture: rx 25525 / 8000000 kb/s, tx 2560 / 1000000 kb/s
    rx = hass.states.get("sensor.bbox_download_bandwidth_occupation")
    tx = hass.states.get("sensor.bbox_upload_bandwidth_occupation")
    assert float(rx.state) == pytest.approx(0.32, abs=0.005)
    assert float(tx.state) == pytest.approx(0.26, abs=0.005)
    assert rx.attributes["unit_of_measurement"] == "%"
    assert "device_class" not in rx.attributes
    assert (
        registry.async_get("sensor.bbox_download_bandwidth_occupation").unique_id
        == f"{BOX_ID}-wan_ip_stats.wan.ip.stats.rx.occupation"
    )

    # raw fields: disabled by default, no unit
    for direction, _expected in (("download", "25"), ("upload", "2")):
        entity_id = f"sensor.bbox_{direction}_occupation_raw"
        assert hass.states.get(entity_id) is None
        entity = registry.async_get(entity_id)
        assert entity.disabled_by is not None
        assert entity.unit_of_measurement is None
        registry.async_update_entity(entity_id, disabled_by=None)
    assert registry.async_get("sensor.bbox_download_occupation_raw").unique_id == (
        f"{BOX_ID}-wan_ip_stats.wan.ip.stats.rx.occupation_raw"
    )
    await hass.config_entries.async_reload(config_entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.bbox_download_occupation_raw").state == "25"
    assert hass.states.get("sensor.bbox_upload_occupation_raw").state == "2"


@pytest.mark.parametrize(
    ("patch", "expected"),
    [
        ({"contractualBandwidth": 0}, STATE_UNKNOWN),
        ({"contractualBandwidth": None}, STATE_UNKNOWN),
        ({"contractualBandwidth": "n/a"}, STATE_UNKNOWN),
        ("missing", STATE_UNKNOWN),
        ({"bandwidth": 99999999}, "100.0"),
        ({"bandwidth": -5}, "0.0"),
        ({"bandwidth": None}, STATE_UNKNOWN),
    ],
)
async def test_occupation_percent_is_bounded_and_defensive(
    hass: HomeAssistant, config_entry: ConfigEntry, router: FakeBox, patch, expected
) -> None:
    """Unknown without a usable contractual bandwidth, clamped to 0-100."""
    # derived variant (anonymous) of the real answer
    stats = copy.deepcopy(PUBLIC_ANSWERS["wan/ip/stats"])
    rx = stats[0]["wan"]["ip"]["stats"]["rx"]
    if patch == "missing":
        del rx["contractualBandwidth"]
    else:
        rx.update(patch)
    router.route("wan/ip/stats", stats)
    await setup_entry(hass, config_entry)
    assert (
        hass.states.get("sensor.bbox_download_bandwidth_occupation").state == expected
    )


# --- c) no POWER_FACTOR ------------------------------------------------------


async def test_percentage_sensors_have_no_device_class(
    hass: HomeAssistant, config_entry: ConfigEntry, router: FakeBox
) -> None:
    """Memory free is a plain percentage; POWER_FACTOR is not used anymore."""
    await setup_entry(hass, config_entry)
    state = hass.states.get("sensor.bbox_memory_free")
    assert state.attributes["unit_of_measurement"] == "%"
    assert "device_class" not in state.attributes
    assert state.attributes["state_class"] == SensorStateClass.MEASUREMENT

    root = Path(__file__).parent.parent / "custom_components"
    for source in root.rglob("*.py"):
        assert "POWER_FACTOR" not in source.read_text(), source


# --- e) error / discard counters --------------------------------------------


@pytest.mark.parametrize("direction", ["download", "upload"])
@pytest.mark.parametrize("kind", ["discard", "error"])
async def test_packet_counters(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    router: FakeBox,
    direction: str,
    kind: str,
) -> None:
    """Error and discard counters: TOTAL_INCREASING, disabled by default."""
    await setup_entry(hass, config_entry)
    entity_id = f"sensor.bbox_{direction}_{kind}_packet"
    entity = er.async_get(hass).async_get(entity_id)
    assert entity.disabled_by is not None
    assert hass.states.get(entity_id) is None
    er.async_get(hass).async_update_entity(entity_id, disabled_by=None)
    await hass.config_entries.async_reload(config_entry.entry_id)
    await hass.async_block_till_done()
    state = hass.states.get(entity_id)
    assert state.state == "0"
    assert state.attributes["state_class"] == SensorStateClass.TOTAL_INCREASING
