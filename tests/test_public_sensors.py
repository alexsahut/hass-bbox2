"""Tests for the public sensors (S6), on the real answers of a F@st 5696b.

The variants of an answer (empty series, Down state...) are derived from the
fixtures in the tests: they contain no personal data.
"""

import copy
import json
import logging
from pathlib import Path

import pytest
from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_DEVICE_CLASS,
    ATTR_UNIT_OF_MEASUREMENT,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    EntityCategory,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from custom_components.bbox.binary_sensor import BINARY_SENSOR_TYPES
from custom_components.bbox.const import DOMAIN
from custom_components.bbox.coordinator import AUTHENTICATED_ENDPOINTS
from custom_components.bbox.sensor import SENSOR_TYPES

from .common import setup_entry
from .conftest import FakeBox
from .const import BOX_ID, PUBLIC_ANSWERS, SERIAL

COMPONENT = Path(__file__).parent.parent / "custom_components" / "bbox"

NEW_BINARY = {
    "summary.wireless.radio": True,
    "summary.wireless.guestenable": False,
    "summary.wireless.guest24enable": False,
    "summary.wireless.guest5enable": False,
    "summary.wireless.compatibility24enable": True,
    "summary.wireless.compatibility5enable": True,
    "wps.wps.enable": True,
    "upnp_igd.upnp.igd.enable": False,
    "wan_ftth_stats.wan.ftth.state": True,
    "wan_ip.wan.ip.ip6state": True,
}
NEW_SENSORS = {
    "wan_ftth_stats.wan.ftth.mode": "1000baseT-HD",
    "wan_ip_stats.wan.ip.stats.rx.contractualBandwidth": 8000000.0,
    "wan_ip_stats.wan.ip.stats.tx.contractualBandwidth": 1000000.0,
    "alerts.alerts.list": 0,
    "summary.hosts": 41,
    "wan_diags.diags.ping": 7.276,
    "wan_diags.diags.dns": 6.377,
    "wan_diags.diags.http": 23.098,
    "lan_stats.lan.stats.rx.bytes": 688558623366,
    "lan_stats.lan.stats.tx.bytes": 4037561751366,
}
DISABLED = {
    "summary.wireless.guest24enable",
    "summary.wireless.guest5enable",
    "summary.wireless.compatibility24enable",
    "summary.wireless.compatibility5enable",
    "wan_diags.diags.dns",
    "wan_diags.diags.http",
    "lan_stats.lan.stats.rx.bytes",
    "lan_stats.lan.stats.tx.bytes",
}

# unique_id (after the LAN MAC address of the box) of every entity before S6
EXISTING_KEYS = {
    "sensor": {
        "info.device.temperature.current",
        "wan_ip_stats.wan.ip.stats.rx.bytes",
        "wan_ip_stats.wan.ip.stats.rx.packetsdiscards",
        "wan_ip_stats.wan.ip.stats.rx.packetserrors",
        "wan_ip_stats.wan.ip.stats.rx.bandwidth",
        "wan_ip_stats.wan.ip.stats.rx.occupation",
        "wan_ip_stats.wan.ip.stats.rx.occupation_raw",
        "wan_ip_stats.wan.ip.stats.tx.bytes",
        "wan_ip_stats.wan.ip.stats.tx.packetsdiscards",
        "wan_ip_stats.wan.ip.stats.tx.packetserrors",
        "wan_ip_stats.wan.ip.stats.tx.bandwidth",
        "wan_ip_stats.wan.ip.stats.tx.occupation",
        "wan_ip_stats.wan.ip.stats.tx.occupation_raw",
        "wan_ip.wan.ip.address",
        "wan_ip.wan.ip.ip6address.0.ipaddress",
        "info.device.numberofboots",
        "info.device.boot_time",
        "memory.device.mem.free",
        "speedtest_infos.speedtest.latestmeasurements.download.0.speed",
    },
    "binary_sensor": {
        "info.device.status",
        *(f"led.ethernetPort.{i}.state" for i in range(5)),
    },
    "button": {"refresh"},
}


def _registry_ids(hass: HomeAssistant, entry: ConfigEntry, domain: str):
    registry = er.async_get(hass)
    return {
        e.unique_id: e
        for e in er.async_entries_for_config_entry(registry, entry.entry_id)
        if e.domain == domain
    }


def _state(hass: HomeAssistant, entry: ConfigEntry, domain: str, key: str):
    entity = _registry_ids(hass, entry, domain)[f"{BOX_ID}-{key}"]
    return hass.states.get(entity.entity_id)


async def _enable_all(hass: HomeAssistant, entry: ConfigEntry) -> None:
    registry = er.async_get(hass)
    for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
        if entity.disabled_by:
            registry.async_update_entity(entity.entity_id, disabled_by=None)
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()


async def test_new_binary_sensors(
    hass: HomeAssistant, config_entry: ConfigEntry, router: FakeBox
) -> None:
    """Every new binary sensor reads its value on the real answers."""
    await setup_entry(hass, config_entry)
    await _enable_all(hass, config_entry)
    assert {d.key for d in BINARY_SENSOR_TYPES} == set(NEW_BINARY)
    for key, expected in NEW_BINARY.items():
        state = _state(hass, config_entry, "binary_sensor", key)
        assert state.state == (STATE_ON if expected else STATE_OFF), key


async def test_new_sensors(
    hass: HomeAssistant, config_entry: ConfigEntry, router: FakeBox
) -> None:
    """Every new sensor reads its value on the real answers."""
    await setup_entry(hass, config_entry)
    await _enable_all(hass, config_entry)
    assert {d.key for d in SENSOR_TYPES} >= set(NEW_SENSORS)
    for key, expected in NEW_SENSORS.items():
        state = _state(hass, config_entry, "sensor", key)
        if key.startswith("lan_stats"):
            # displayed in GB (suggested unit), stored in bytes
            assert state.attributes[ATTR_UNIT_OF_MEASUREMENT] == "GB"
            assert float(state.state) == pytest.approx(expected / 1e9, rel=1e-3), key
        elif isinstance(expected, str):
            assert state.state == expected, key
        else:
            assert float(state.state) == pytest.approx(expected), key


async def test_sensor_classes_and_defaults(
    hass: HomeAssistant, config_entry: ConfigEntry, router: FakeBox
) -> None:
    """Classes, units, state classes, categories and default activation."""
    await setup_entry(hass, config_entry)
    ids = {
        **_registry_ids(hass, config_entry, "sensor"),
        **_registry_ids(hass, config_entry, "binary_sensor"),
    }
    for key in (*NEW_BINARY, *NEW_SENSORS):
        entity = ids[f"{BOX_ID}-{key}"]
        assert bool(entity.disabled_by) == (key in DISABLED), key

    by_key = {d.key: d for d in SENSOR_TYPES}
    for key in ("ping", "dns", "http"):
        d = by_key[f"wan_diags.diags.{key}"]
        assert d.device_class == SensorDeviceClass.DURATION
        assert d.native_unit_of_measurement == "ms"
        assert d.state_class == SensorStateClass.MEASUREMENT
    for direction in ("rx", "tx"):
        d = by_key[f"lan_stats.lan.stats.{direction}.bytes"]
        assert d.device_class == SensorDeviceClass.DATA_SIZE
        assert d.state_class == SensorStateClass.TOTAL_INCREASING
        d = by_key[f"wan_ip_stats.wan.ip.stats.{direction}.contractualBandwidth"]
        assert d.device_class == SensorDeviceClass.DATA_RATE
        assert d.native_unit_of_measurement == "kbit/s"  # as the S3 sensors
    assert (
        by_key["wan_ftth_stats.wan.ftth.mode"].entity_category
        == EntityCategory.DIAGNOSTIC
    )
    sentinel = next(d for d in BINARY_SENSOR_TYPES if d.key.startswith("upnp_igd"))
    assert sentinel.device_class == BinarySensorDeviceClass.PROBLEM
    state = _state(hass, config_entry, "sensor", "summary.hosts")
    # no name and no address of the devices in the attributes
    assert set(state.attributes) <= {"state_class", "icon", "friendly_name"}


async def test_translations_cover_every_new_entity() -> None:
    """strings.json, en.json and fr.json name every new entity."""
    for name in ("strings.json", "translations/en.json", "translations/fr.json"):
        entity = json.loads((COMPONENT / name).read_text())["entity"]
        for domain, descriptions in (
            ("sensor", [d for d in SENSOR_TYPES if d.translation_key]),
            ("binary_sensor", list(BINARY_SENSOR_TYPES)),
        ):
            assert {d.translation_key for d in descriptions} == set(entity[domain]), (
                name,
                domain,
            )
            assert all(entity[domain][k]["name"] for k in entity[domain])


async def test_unique_ids_of_existing_entities_are_frozen(
    hass: HomeAssistant, config_entry: ConfigEntry, router: FakeBox
) -> None:
    """Every entity keeps its key; the prefix is the LAN MAC address of the box."""
    await setup_entry(hass, config_entry)
    for domain, keys in EXISTING_KEYS.items():
        registered = set(_registry_ids(hass, config_entry, domain))
        assert {f"{BOX_ID}-{key}" for key in keys} <= registered, domain
        if domain != "button":
            # the other unique_ids are the new ones, built the same way
            new = NEW_BINARY if domain == "binary_sensor" else NEW_SENSORS
            assert registered - {f"{BOX_ID}-{key}" for key in keys} == {
                f"{BOX_ID}-{key}" for key in new
            }
    trackers = set(_registry_ids(hass, config_entry, "device_tracker"))
    # the unique_id of a tracker is the MAC address (ScannerEntity)
    assert trackers == {"00:01:02:03:04:0e", "01:02:03:04:05:06", "01:02:03:04:05:f9"}


async def test_unique_ids_do_not_depend_on_the_password(
    hass: HomeAssistant, config_entry: ConfigEntry, router: FakeBox
) -> None:
    """Removing the password keeps the box device and the public entities."""
    await setup_entry(hass, config_entry)
    registry = er.async_get(hass)
    before = {
        e.unique_id: e.entity_id
        for e in er.async_entries_for_config_entry(registry, config_entry.entry_id)
        if e.domain in ("sensor", "binary_sensor", "button")
    }
    device_registry = dr.async_get(hass)
    box = device_registry.async_get_device_by_identifier(
        (DOMAIN, BOX_ID), config_entry.entry_id
    )
    assert box.serial_number == SERIAL  # read in `device` with the password

    router.route("device", PUBLIC_ANSWERS["device"])  # no serial number without it
    hass.config_entries.async_update_entry(
        config_entry, data={**config_entry.data, "password": ""}
    )
    await hass.config_entries.async_reload(config_entry.entry_id)
    await hass.async_block_till_done()

    after = {
        e.unique_id: e.entity_id
        for e in er.async_entries_for_config_entry(registry, config_entry.entry_id)
        if e.domain in ("sensor", "binary_sensor", "button")
    }
    # same unique_ids and entity_ids: only the sensors needing a password are gone
    assert after == {uid: eid for uid, eid in before.items() if "speedtest" not in uid}
    assert all(uid.startswith(f"{BOX_ID}-") for uid in after)
    devices = dr.async_entries_for_config_entry(device_registry, config_entry.entry_id)
    assert [d.id for d in devices if (DOMAIN, BOX_ID) in d.identifiers] == [box.id]
    assert config_entry.unique_id == BOX_ID


def test_no_placeholder_identifier_in_the_code() -> None:
    """The identifier of the box is never a fixed placeholder value."""
    for path in COMPONENT.rglob("*.py"):
        assert "ABC12345" not in path.read_text(), path


async def test_no_password_creates_only_public_entities(
    hass: HomeAssistant,
    public_config_entry: ConfigEntry,
    public_router: FakeBox,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Without password: public endpoints only, public entities, no error."""
    caplog.set_level(logging.INFO)
    await setup_entry(hass, public_config_entry)
    await public_config_entry.runtime_data.async_refresh()

    authenticated = {e.path for e in AUTHENTICATED_ENDPOINTS}
    assert not public_router.endpoints & authenticated
    assert ("POST", "login") not in public_router.requests
    assert public_router.endpoints  # sanity

    registry = er.async_get(hass)
    entries = er.async_entries_for_config_entry(registry, public_config_entry.entry_id)
    assert not [e for e in entries if e.domain == "device_tracker"]
    assert not [e for e in entries if "speedtest" in e.unique_id]
    unique_ids = {e.unique_id for e in entries}
    for key in (*NEW_BINARY, *NEW_SENSORS):
        assert f"{BOX_ID}-{key}" in unique_ids, key
    # every public entity has a state read from the box (none unavailable)
    for entity in entries:
        if entity.disabled_by is None:
            state = hass.states.get(entity.entity_id)
            assert state.state != STATE_UNAVAILABLE, entity.entity_id
    assert hass.states.get("sensor.bbox_known_devices").state == "41"
    assert "401" not in caplog.text
    assert not [
        r
        for r in caplog.records
        if r.levelno >= logging.WARNING and r.name.startswith("custom_components")
    ]


async def test_wan_diags_404_only_affects_the_latencies(
    hass: HomeAssistant,
    public_config_entry: ConfigEntry,
    public_router: FakeBox,
) -> None:
    """A missing endpoint makes only its own entities unavailable."""
    public_router.route("wan/diags", status=404)
    await setup_entry(hass, public_config_entry)
    await public_config_entry.runtime_data.async_refresh()

    assert public_router.count("wan/diags") == 1  # a 404 is not requested again
    entities = er.async_entries_for_config_entry(
        er.async_get(hass), public_config_entry.entry_id
    )
    for entity in entities:
        if entity.disabled_by:
            continue
        state = hass.states.get(entity.entity_id).state
        if "wan_diags" in entity.unique_id:
            assert state == STATE_UNAVAILABLE, entity.entity_id
        else:
            assert state != STATE_UNAVAILABLE, entity.entity_id


async def test_lan_stats_error_only_affects_the_lan_traffic(
    hass: HomeAssistant, config_entry: ConfigEntry, router: FakeBox
) -> None:
    """An error of lan/stats does not touch the other endpoints' entities."""
    router.route("lan/stats", status=500)
    await setup_entry(hass, config_entry)
    await _enable_all(hass, config_entry)
    assert (
        _state(hass, config_entry, "sensor", "lan_stats.lan.stats.rx.bytes").state
        == STATE_UNAVAILABLE
    )
    assert _state(hass, config_entry, "sensor", "wan_diags.diags.ping").state != (
        STATE_UNAVAILABLE
    )


def _diags(**series) -> list:
    answer = copy.deepcopy(PUBLIC_ANSWERS["wan/diags"])
    answer[0]["diags"].update(series)
    return answer


def _point(average=7000, tries=10, success=10):
    return {
        "min": 1,
        "max": 2,
        "average": average,
        "success": success,
        "error": 0,
        "tries": tries,
        "status": "OK",
        "protocol": "IPv4",
    }


@pytest.mark.parametrize(
    ("series", "expected"),
    [
        # the last point is the one used, in ms (the box gives µs)
        ([_point(1000), _point(2500)], "2.5"),
        # the last point without any try: no 0 ms
        ([_point(1000), _point(0, tries=0, success=0)], STATE_UNKNOWN),
        # tries but no success
        ([_point(0, tries=5, success=0)], STATE_UNKNOWN),
        # empty series, or a point which is not a point
        ([], STATE_UNKNOWN),
        (["x"], STATE_UNKNOWN),
        # average missing
        ([{"tries": 3, "success": 3}], STATE_UNKNOWN),
    ],
)
async def test_latency_last_point(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    router: FakeBox,
    series: list,
    expected: str,
) -> None:
    """The latency is the last point of the series, unknown without measurement."""
    router.route("wan/diags", _diags(ping=series))
    await setup_entry(hass, config_entry)
    state = _state(hass, config_entry, "sensor", "wan_diags.diags.ping")
    assert state.state == expected
    assert state.attributes[ATTR_DEVICE_CLASS] == "duration"


async def test_latency_series_missing(
    hass: HomeAssistant, config_entry: ConfigEntry, router: FakeBox
) -> None:
    """A series which is not a list gives an unknown state."""
    router.route("wan/diags", [{"diags": {"ping": None}}])
    await setup_entry(hass, config_entry)
    assert (
        _state(hass, config_entry, "sensor", "wan_diags.diags.ping").state
        == STATE_UNKNOWN
    )


def _wan_ip(**ip) -> list:
    answer = copy.deepcopy(PUBLIC_ANSWERS["wan/ip"])
    answer[0]["wan"]["ip"].update(ip)
    return answer


@pytest.mark.parametrize(
    ("ip", "expected"),
    [
        ({}, STATE_ON),
        ({"ip6state": "Down"}, STATE_OFF),
        # up but no address in Preferred state (tentative, deprecated...)
        (
            {"ip6address": [{"ipaddress": "2001:db8::1", "status": "Tentative"}]},
            STATE_OFF,
        ),
        ({"ip6address": []}, STATE_OFF),
        ({"ip6address": "none"}, STATE_OFF),
        (
            {
                "ip6address": [
                    {"status": "Deprecated"},
                    "x",
                    {"status": "preferred"},
                ]
            },
            STATE_ON,
        ),
        ({"ip6state": None}, STATE_UNKNOWN),
    ],
)
async def test_ipv6_rule(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    router: FakeBox,
    ip: dict,
    expected: str,
) -> None:
    """IPv6 is on when ip6state is Up AND an address is Preferred."""
    router.route("wan/ip", _wan_ip(**ip))
    await setup_entry(hass, config_entry)
    state = _state(hass, config_entry, "binary_sensor", "wan_ip.wan.ip.ip6state")
    assert state.state == expected


async def test_upnp_enabled_is_a_problem(
    hass: HomeAssistant, config_entry: ConfigEntry, router: FakeBox
) -> None:
    """UPnP IGD enabled is shown as a problem (on), disabled is off."""
    upnp = copy.deepcopy(PUBLIC_ANSWERS["upnp/igd"])
    upnp[0]["upnp"]["igd"]["enable"] = 1
    router.route("upnp/igd", upnp)
    await setup_entry(hass, config_entry)
    state = _state(hass, config_entry, "binary_sensor", "upnp_igd.upnp.igd.enable")
    assert state.state == STATE_ON
    assert state.attributes[ATTR_DEVICE_CLASS] == "problem"


async def test_wifi_flags_and_ftth_down(
    hass: HomeAssistant, config_entry: ConfigEntry, router: FakeBox
) -> None:
    """The Wi-Fi flags follow `summary`, the FTTH link follows its state."""
    summary = copy.deepcopy(PUBLIC_ANSWERS["summary"])
    summary[0]["wireless"].update(radio=0, guestenable=1, guest24enable=1)
    router.route("summary", summary)
    ftth = copy.deepcopy(PUBLIC_ANSWERS["wan/ftth/stats"])
    ftth[0]["wan"]["ftth"]["state"] = "Down"
    router.route("wan/ftth/stats", ftth)
    wps = copy.deepcopy(PUBLIC_ANSWERS["wireless/wps"])
    wps[0]["wps"]["enable"] = 0
    router.route("wireless/wps", wps)
    await setup_entry(hass, config_entry)
    await _enable_all(hass, config_entry)

    def on(key):
        return _state(hass, config_entry, "binary_sensor", key).state

    assert on("summary.wireless.radio") == STATE_OFF
    assert on("summary.wireless.guestenable") == STATE_ON
    assert on("summary.wireless.guest24enable") == STATE_ON
    assert on("wps.wps.enable") == STATE_OFF
    assert on("wan_ftth_stats.wan.ftth.state") == STATE_OFF


async def test_missing_values_give_unknown(
    hass: HomeAssistant, config_entry: ConfigEntry, router: FakeBox
) -> None:
    """A value missing from an answer gives an unknown state, not an error."""
    router.route("summary", [{"wireless": {}, "hosts": "?"}])
    router.route("lan/stats", [{"lan": {"stats": {"rx": {"bytes": "x"}}}}])
    router.route("wan/ftth/stats", [{"wan": {}}])
    await setup_entry(hass, config_entry)
    await _enable_all(hass, config_entry)
    for domain, key in (
        ("binary_sensor", "summary.wireless.radio"),
        ("binary_sensor", "wan_ftth_stats.wan.ftth.state"),
        ("sensor", "summary.hosts"),
        ("sensor", "lan_stats.lan.stats.rx.bytes"),
        ("sensor", "wan_ftth_stats.wan.ftth.mode"),
    ):
        assert _state(hass, config_entry, domain, key).state == STATE_UNKNOWN, key


@pytest.mark.parametrize(
    ("alerts", "summary_alerts", "expected"),
    [
        ([{"id": 1}, {"id": 2}], {"count": 0}, "2"),  # alerts.list wins
        (None, {"count": 3}, "3"),  # endpoint absent: summary.alerts.count
        (None, {"count": True}, STATE_UNKNOWN),
        (None, {}, STATE_UNKNOWN),
    ],
)
async def test_alerts_count(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    router: FakeBox,
    alerts: list | None,
    summary_alerts: dict,
    expected: str,
) -> None:
    """Alerts: length of alerts.list, `summary.alerts.count` as a fallback."""
    summary = copy.deepcopy(PUBLIC_ANSWERS["summary"])
    summary[0]["alerts"] = summary_alerts
    router.route("summary", summary)
    if alerts is None:
        router.route("alerts", status=404)
    else:
        router.route("alerts", [{"alerts": {"list": alerts}}])
    await setup_entry(hass, config_entry)
    assert _state(hass, config_entry, "sensor", "alerts.alerts.list").state == expected
