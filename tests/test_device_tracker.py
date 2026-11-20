"""Tests of the device trackers (they need the hosts, so a password)."""

import pytest
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_HOME, STATE_NOT_HOME, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .common import setup_entry
from .conftest import FakeBox
from .const import AUTHENTICATED_ANSWERS, BOX_ID

HOSTS = AUTHENTICATED_ANSWERS["hosts"]


async def enable_trackers(hass: HomeAssistant, entry: ConfigEntry) -> list[str]:
    """Enable the trackers (disabled by default) and reload the entry."""
    registry = er.async_get(hass)
    trackers = [
        e.entity_id
        for e in er.async_entries_for_config_entry(registry, entry.entry_id)
        if e.domain == "device_tracker"
    ]
    for entity_id in trackers:
        registry.async_update_entity(entity_id, disabled_by=None)
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    return trackers


async def test_trackers_with_password(
    hass: HomeAssistant, config_entry: ConfigEntry, router: FakeBox
) -> None:
    """One tracker per host, from `hosts`."""
    await setup_entry(hass, config_entry)
    trackers = await enable_trackers(hass, config_entry)

    assert len(trackers) == 3
    assert hass.states.get("device_tracker.host_001").state == STATE_HOME
    assert hass.states.get("device_tracker.host_006").state == STATE_NOT_HOME


async def test_no_tracker_without_password(
    hass: HomeAssistant, public_config_entry: ConfigEntry, public_router: FakeBox
) -> None:
    """Without password there is no tracker, hosts is not requested."""
    await setup_entry(hass, public_config_entry)

    registry = er.async_get(hass)
    assert not [
        e
        for e in er.async_entries_for_config_entry(
            registry, public_config_entry.entry_id
        )
        if e.domain == "device_tracker"
    ]
    assert "hosts" not in public_router.endpoints


async def test_trackers_removed_when_the_password_is_removed(
    hass: HomeAssistant, config_entry: ConfigEntry, router: FakeBox
) -> None:
    """The trackers created with a password disappear without password."""
    await setup_entry(hass, config_entry)
    await enable_trackers(hass, config_entry)
    assert hass.states.async_entity_ids("device_tracker")

    hass.config_entries.async_update_entry(
        config_entry, data={**config_entry.data, "password": ""}
    )
    await hass.async_block_till_done()

    registry = er.async_get(hass)
    assert not [
        e
        for e in er.async_entries_for_config_entry(registry, config_entry.entry_id)
        if e.domain == "device_tracker"
    ]


async def test_trackers_survive_a_hosts_failure(
    hass: HomeAssistant, config_entry: ConfigEntry, router: FakeBox
) -> None:
    """When hosts fails the trackers are unavailable, then recover; no error."""
    await setup_entry(hass, config_entry)
    await enable_trackers(hass, config_entry)

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
    await enable_trackers(hass, config_entry)

    router.route("hosts", [{"hosts": {"list": []}}])
    await config_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    state = hass.states.get("device_tracker.host_001")
    assert state.state == STATE_NOT_HOME
    assert state.attributes["mac"] == "00:01:02:03:04:0e"
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
    trackers = await enable_trackers(hass, public_config_entry)
    assert len(trackers) == 3
    assert hass.states.get("device_tracker.host_001").state == STATE_HOME
