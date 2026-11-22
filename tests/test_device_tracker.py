"""Tests of the device trackers (they need the hosts, so a password)."""

from typing import Any

import pytest
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import STATE_HOME, STATE_NOT_HOME, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.bbox.const import DOMAIN

from .common import setup_entry
from .conftest import FakeBox
from .const import AUTHENTICATED_ANSWERS, BOX_ID, SYNTHETIC_HOSTS

HOSTS = AUTHENTICATED_ANSWERS["hosts"]
MAC_1 = "00:01:02:03:04:0e"
MAC_4 = "01:02:03:04:05:f9"
MAC_6 = "01:02:03:04:05:06"


def smac(n: int) -> str:
    """MAC of the synthetic hosts."""
    return f"02:00:00:00:00:{n:02x}"


@pytest.fixture(name="options")
def get_options() -> dict[str, Any]:
    """The three hosts of the test data are tracked (none is by default)."""
    return {"tracked_devices": [MAC_1, MAC_4, MAC_6]}


def trackers(hass: HomeAssistant, entry: ConfigEntry) -> list[er.RegistryEntry]:
    return [
        e
        for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
        if e.domain == "device_tracker"
    ]


def devices(hass: HomeAssistant, entry: ConfigEntry) -> list[dr.DeviceEntry]:
    return dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)


def host_devices(hass: HomeAssistant, entry: ConfigEntry) -> list[dr.DeviceEntry]:
    return [d for d in devices(hass, entry) if (DOMAIN, BOX_ID) not in d.identifiers]


async def test_trackers_of_the_chosen_hosts(
    hass: HomeAssistant, config_entry: ConfigEntry, router: FakeBox
) -> None:
    """One enabled tracker and one device per chosen host, named after `hosts`."""
    await setup_entry(hass, config_entry)

    assert len(trackers(hass, config_entry)) == 3
    assert all(e.disabled_by is None for e in trackers(hass, config_entry))
    assert hass.states.get("device_tracker.host_001").state == STATE_HOME
    assert hass.states.get("device_tracker.host_006").state == STATE_NOT_HOME
    assert hass.states.get("device_tracker.host_001").attributes["friendly_name"] == (
        "Host-001"
    )
    hosts = {d.name: d for d in host_devices(hass, config_entry)}
    assert set(hosts) == {"Host-001", "Host-004", "Host-006"}
    box = dr.async_get(hass).async_get_device_by_identifier(
        (DOMAIN, BOX_ID), config_entry.entry_id
    )
    device = hosts["Host-001"]
    # the identifier is the one of 2.0.1, the tracker is attached to the device
    assert device.identifiers == {(DOMAIN, f"{BOX_ID}_00_01_02_03_04_0e")}
    assert (dr.CONNECTION_NETWORK_MAC, MAC_1) in device.connections
    assert device.via_device_id == box.id
    entity = er.async_get(hass).async_get("device_tracker.host_001")
    assert entity.unique_id == MAC_1
    assert entity.device_id == device.id


@pytest.mark.parametrize("options", [{}, {"tracked_devices": []}])
async def test_no_tracker_by_default(
    hass: HomeAssistant, config_entry: ConfigEntry, router: FakeBox
) -> None:
    """By default: no tracker, the Bbox is the only device of the entry."""
    await setup_entry(hass, config_entry)

    assert config_entry.state == ConfigEntryState.LOADED
    assert not trackers(hass, config_entry)
    assert [d.identifiers for d in devices(hass, config_entry)] == [{(DOMAIN, BOX_ID)}]


async def test_names_of_the_synthetic_hosts(
    hass: HomeAssistant, config_entry: ConfigEntry, router: FakeBox
) -> None:
    """Readable names, never the MAC when there is information, duplicates suffixed."""
    chosen = [smac(1), smac(2), smac(4), smac(6), smac(11)]
    hass.config_entries.async_update_entry(
        config_entry, options={"tracked_devices": chosen}
    )
    router.route("hosts", SYNTHETIC_HOSTS)
    await setup_entry(hass, config_entry)

    names = {d.name for d in host_devices(hass, config_entry)}
    # 02 is a duplicate of 03 (not chosen): the suffix is the same in the options
    assert names == {
        "synth-laptop",
        "Acme Phone X (0002)",
        "Cam-1",
        smac(6),
        "dup-host (000B)",
    }
    assert hass.states.get("device_tracker.cam_1").state == STATE_HOME
    assert hass.states.get("device_tracker.acme_phone_x_0002") is not None


async def test_name_by_user_is_kept(
    hass: HomeAssistant, config_entry: ConfigEntry, router: FakeBox
) -> None:
    """A device renamed by the user is not renamed again, at any load."""
    await setup_entry(hass, config_entry)
    registry = dr.async_get(hass)
    device = registry.async_get_device_by_identifier(
        (DOMAIN, f"{BOX_ID}_00_01_02_03_04_0e"), config_entry.entry_id
    )
    registry.async_update_device(device.id, name_by_user="My server")

    assert await hass.config_entries.async_reload(config_entry.entry_id)
    await hass.async_block_till_done()

    device = registry.async_get(device.id)
    assert device.name_by_user == "My server"
    assert device.name == "Host-001"


async def test_integration_disabled_tracker_is_enabled(
    hass: HomeAssistant, config_entry: ConfigEntry, router: FakeBox
) -> None:
    """A tracker of a chosen host disabled by the integration (2.0.1) is enabled;
    one disabled by the user stays disabled."""
    registry = er.async_get(hass)
    for mac, disabler in (
        (MAC_1, er.RegistryEntryDisabler.INTEGRATION),
        (MAC_4, er.RegistryEntryDisabler.USER),
    ):
        registry.async_get_or_create(
            "device_tracker",
            DOMAIN,
            mac,
            config_entry=config_entry,
            disabled_by=disabler,
        )
    await setup_entry(hass, config_entry)

    by_mac = {e.unique_id: e for e in trackers(hass, config_entry)}
    assert by_mac[MAC_1].disabled_by is None
    assert by_mac[MAC_4].disabled_by is er.RegistryEntryDisabler.USER
    assert by_mac[MAC_6].disabled_by is None
    assert hass.states.get(by_mac[MAC_1].entity_id) is not None
    assert hass.states.get(by_mac[MAC_4].entity_id) is None


async def test_cleanup_of_the_trackers_of_2_0_1(
    hass: HomeAssistant, config_entry: ConfigEntry, router: FakeBox
) -> None:
    """93 trackers and devices created by 2.0.1: only the chosen host remains."""
    config_entry_options = {"tracked_devices": [MAC_1]}
    hass.config_entries.async_update_entry(config_entry, options=config_entry_options)
    entities = er.async_get(hass)
    devs = dr.async_get(hass)
    other = MockConfigEntry(domain="other", entry_id="other_entry")
    other.add_to_hass(hass)
    box = devs.async_get_or_create(
        config_entry_id=config_entry.entry_id, identifiers={(DOMAIN, BOX_ID)}
    )
    sensor = entities.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{BOX_ID}-alerts",
        config_entry=config_entry,
        device_id=box.id,
    )
    other_tracker = entities.async_get_or_create(
        "device_tracker", "other", "02:00:00:00:99:99", config_entry=other
    )
    for n in range(93):
        mac = f"02:00:00:00:01:{n:02x}"
        entities.async_get_or_create(
            "device_tracker",
            DOMAIN,
            mac,
            config_entry=config_entry,
            disabled_by=er.RegistryEntryDisabler.INTEGRATION,
        )
        devs.async_get_or_create(
            config_entry_id=config_entry.entry_id,
            identifiers={(DOMAIN, f"{BOX_ID}_{mac.replace(':', '_')}")},
            connections={(dr.CONNECTION_NETWORK_MAC, mac)},
            name=mac,
        )
    # the device of another integration with the MAC address of a host of 2.0.1
    shared = devs.async_get_or_create(
        config_entry_id=other.entry_id,
        connections={(dr.CONNECTION_NETWORK_MAC, "02:00:00:00:01:05")},
        name="Shared",
    )
    # a device of the entry known only by its MAC, as Home Assistant creates it
    devs.async_get_or_create(
        config_entry_id=config_entry.entry_id,
        connections={(dr.CONNECTION_NETWORK_MAC, "02:00:00:00:03:03")},
    )
    assert len(host_devices(hass, config_entry)) == 94

    await setup_entry(hass, config_entry)

    assert [e.unique_id for e in trackers(hass, config_entry)] == [MAC_1]
    assert [d.name for d in host_devices(hass, config_entry)] == ["Host-001"]
    # the device of the other integration is another device: not touched
    shared = devs.async_get(shared.id)
    assert shared.config_entry_id == other.entry_id
    assert shared.name == "Shared"
    assert devs.async_get(box.id) is not None
    assert entities.async_get(sensor.entity_id) is not None
    assert entities.async_get(other_tracker.entity_id) is not None
    assert hass.states.get("sensor.bbox_ip_address").state == "203.0.113.46"
    # nothing is recreated for the 93 hosts
    assert hass.states.get("device_tracker.host_004") is None

    # idempotent: a second load changes nothing
    before = (
        {e.entity_id for e in er.async_entries_for_config_entry(entities, "123456")},
        {d.id for d in devices(hass, config_entry)},
    )
    assert await hass.config_entries.async_reload(config_entry.entry_id)
    await hass.async_block_till_done()
    assert before == (
        {e.entity_id for e in er.async_entries_for_config_entry(entities, "123456")},
        {d.id for d in devices(hass, config_entry)},
    )


async def test_chosen_host_missing_from_the_box_is_kept(
    hass: HomeAssistant, config_entry: ConfigEntry, router: FakeBox
) -> None:
    """A chosen host which the box does not list now keeps its registry entries."""
    await setup_entry(hass, config_entry)
    assert len(trackers(hass, config_entry)) == 3

    router.route("hosts", [{"hosts": {"list": [HOSTS[0]["hosts"]["list"][0]]}}])
    assert await hass.config_entries.async_reload(config_entry.entry_id)
    await hass.async_block_till_done()

    assert len(trackers(hass, config_entry)) == 3
    assert len(host_devices(hass, config_entry)) == 3


async def test_device_of_another_integration_is_left_alone(
    hass: HomeAssistant, config_entry: ConfigEntry, router: FakeBox
) -> None:
    """A chosen host known to another integration: the Bbox has its own device
    (a device belongs to one config entry); the other one is not renamed."""
    other = MockConfigEntry(domain="other")
    other.add_to_hass(hass)
    known = dr.async_get(hass).async_get_or_create(
        config_entry_id=other.entry_id,
        connections={(dr.CONNECTION_NETWORK_MAC, MAC_1)},
        name="Other name",
    )
    await setup_entry(hass, config_entry)

    assert {d.name for d in host_devices(hass, config_entry)} == {
        "Host-001",
        "Host-004",
        "Host-006",
    }
    assert dr.async_get(hass).async_get(known.id).name == "Other name"
    assert hass.states.get("device_tracker.host_001").state == STATE_HOME


async def test_nothing_without_password(
    hass: HomeAssistant, public_config_entry: ConfigEntry, public_router: FakeBox
) -> None:
    """Without password, whatever the option: no tracker, no host device, and
    those of an earlier load with a password are removed."""
    entities = er.async_get(hass)
    devs = dr.async_get(hass)
    entities.async_get_or_create(
        "device_tracker", DOMAIN, MAC_1, config_entry=public_config_entry
    )
    devs.async_get_or_create(
        config_entry_id=public_config_entry.entry_id,
        identifiers={(DOMAIN, f"{BOX_ID}_00_01_02_03_04_0e")},
        connections={(dr.CONNECTION_NETWORK_MAC, MAC_1)},
    )
    await setup_entry(hass, public_config_entry)

    assert not trackers(hass, public_config_entry)
    assert [d.identifiers for d in devices(hass, public_config_entry)] == [
        {(DOMAIN, BOX_ID)}
    ]
    assert "hosts" not in public_router.endpoints


async def test_trackers_removed_when_the_password_is_removed(
    hass: HomeAssistant, config_entry: ConfigEntry, router: FakeBox
) -> None:
    """The trackers and devices created with a password disappear without."""
    await setup_entry(hass, config_entry)
    assert hass.states.async_entity_ids("device_tracker")

    hass.config_entries.async_update_entry(
        config_entry, data={**config_entry.data, "password": ""}
    )
    await hass.async_block_till_done()

    assert not trackers(hass, config_entry)
    assert not host_devices(hass, config_entry)


async def test_trackers_survive_a_hosts_failure(
    hass: HomeAssistant, config_entry: ConfigEntry, router: FakeBox
) -> None:
    """When hosts fails the trackers are unavailable, then recover; no error."""
    await setup_entry(hass, config_entry)

    router.route("hosts", status=500)
    await config_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get("device_tracker.host_001").state == STATE_UNAVAILABLE
    assert hass.states.get("sensor.bbox_ip_address").state == "203.0.113.46"

    router.route("hosts", HOSTS)
    await config_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get("device_tracker.host_001").state == STATE_HOME


async def test_tracker_of_a_vanished_host(
    hass: HomeAssistant, config_entry: ConfigEntry, router: FakeBox
) -> None:
    """A host which leaves the list does not raise (mac and ip stay readable)."""
    await setup_entry(hass, config_entry)

    router.route("hosts", [{"hosts": {"list": []}}])
    await config_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    state = hass.states.get("device_tracker.host_001")
    assert state.state == STATE_NOT_HOME
    assert state.attributes["mac"] == MAC_1
    assert "ip" not in state.attributes or state.attributes["ip"] is None


@pytest.mark.parametrize("hosts", [[{"hosts": {}}], [{}]])
async def test_hosts_without_list(
    hass: HomeAssistant, config_entry: ConfigEntry, router: FakeBox, hosts
) -> None:
    """A `hosts` answer without list creates no tracker."""
    router.route("hosts", hosts)
    await setup_entry(hass, config_entry)
    assert not hass.states.async_entity_ids("device_tracker")


async def test_reconfigure_adds_the_password(
    hass: HomeAssistant, public_config_entry: ConfigEntry, router: FakeBox
) -> None:
    """Adding the password with Reconfigure: same unique_ids, trackers appear."""
    await setup_entry(hass, public_config_entry)
    registry = er.async_get(hass)
    before = {
        e.unique_id: e.entity_id
        for e in er.async_entries_for_config_entry(
            registry, public_config_entry.entry_id
        )
    }
    assert before
    assert not [uid for uid, eid in before.items() if eid.startswith("device_tracker")]

    result = await public_config_entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "host": "mabbox.bytel.fr",
            "password": "mock_password",
            "use_tls": True,
            "verify_ssl": True,
        },
    )
    await hass.async_block_till_done()

    assert result["reason"] == "reconfigure_successful"
    assert public_config_entry.unique_id == BOX_ID
    after = {
        e.unique_id: e.entity_id
        for e in er.async_entries_for_config_entry(
            registry, public_config_entry.entry_id
        )
    }
    # the public entities are kept, with the same unique_id and entity_id
    assert before.items() <= after.items()
    assert len(trackers(hass, public_config_entry)) == 3
    assert hass.states.get("device_tracker.host_001").state == STATE_HOME
