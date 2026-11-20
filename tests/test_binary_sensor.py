"""Tests for the Bbox binary sensor platform."""

import copy

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .common import setup_entry
from .conftest import FakeBox
from .const import BOX_ID, DEVICE_WITH_SERIAL, PUBLIC_ANSWERS


def _port_entities(registry, config_entry):
    return [
        e
        for e in er.async_entries_for_config_entry(registry, config_entry.entry_id)
        if e.entity_id.startswith("binary_sensor.bbox_ethernet_port")
    ]


async def test_binary_sensor_link_status(
    hass: HomeAssistant, config_entry: ConfigEntry, router: FakeBox
) -> None:
    """The link status is the WAN link state of wan/ip (`wan.link.state`)."""
    await setup_entry(hass, config_entry)
    assert hass.states.get("binary_sensor.bbox_link_status").state == STATE_ON
    entity = er.async_get(hass).async_get("binary_sensor.bbox_link_status")
    assert entity.unique_id == f"{BOX_ID}-info.device.status"

    # device.status (box state) no longer matters
    device = copy.deepcopy(DEVICE_WITH_SERIAL)
    device[0]["device"]["status"] = 0
    router.route("device", device)
    wan_ip = copy.deepcopy(PUBLIC_ANSWERS["wan/ip"])
    wan_ip[0]["wan"]["link"]["state"] = "Down"
    router.route("wan/ip", wan_ip)
    await config_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    assert hass.states.get("binary_sensor.bbox_link_status").state == STATE_OFF


async def test_link_status_unavailable_without_wan_ip(
    hass: HomeAssistant, config_entry: ConfigEntry, router: FakeBox
) -> None:
    """The link status depends on wan/ip only."""
    router.route("wan/ip", status=500)
    await setup_entry(hass, config_entry)
    assert hass.states.get("binary_sensor.bbox_link_status").state == STATE_UNAVAILABLE


async def test_ethernet_ports_5696b(
    hass: HomeAssistant, config_entry: ConfigEntry, router: FakeBox
) -> None:
    """The ethernet ports come from device/led (disabled by default)."""
    await setup_entry(hass, config_entry)
    registry = er.async_get(hass)
    ports = [
        e
        for e in er.async_entries_for_config_entry(registry, config_entry.entry_id)
        if e.entity_id.startswith("binary_sensor.bbox_ethernet_port")
    ]
    assert len(ports) == 5
    for entity in ports:
        registry.async_update_entity(entity.entity_id, disabled_by=None)
    await hass.config_entries.async_reload(config_entry.entry_id)
    await hass.async_block_till_done()

    # device_led.json: ports 3 and 4 are Up
    states = [
        hass.states.get(f"binary_sensor.bbox_ethernet_port_{i}").state
        for i in range(1, 6)
    ]
    assert states == [STATE_OFF, STATE_OFF, STATE_ON, STATE_ON, STATE_OFF]


async def test_ethernet_ports_unavailable_without_led(
    hass: HomeAssistant, config_entry: ConfigEntry, router: FakeBox
) -> None:
    """A failing device/led only affects the ports, which recover with it."""
    await setup_entry(hass, config_entry)
    registry = er.async_get(hass)
    registry.async_update_entity("binary_sensor.bbox_ethernet_port_1", disabled_by=None)
    await hass.config_entries.async_reload(config_entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.bbox_ethernet_port_1").state == STATE_OFF

    router.route("device/led", status=500)
    await config_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert (
        hass.states.get("binary_sensor.bbox_ethernet_port_1").state == STATE_UNAVAILABLE
    )
    assert hass.states.get("binary_sensor.bbox_link_status").state == STATE_ON

    # the endpoint answers again
    router.route("device/led", [{"ethernetPort": [{"id": 1, "state": "Up"}]}])
    await config_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.bbox_ethernet_port_1").state == STATE_ON


async def test_ethernet_ports_follow_the_box(
    hass: HomeAssistant, config_entry: ConfigEntry, router: FakeBox
) -> None:
    """One sensor per port reported by device/led, with the unique_ids of before."""
    # derived variant (anonymous): the box reports 3 ports, ids 1, 2 and 4
    router.route(
        "device/led",
        [{"ethernetPort": [{"id": 1, "state": "Up"}, {"id": 2, "state": "Down"}]}],
    )
    await setup_entry(hass, config_entry)
    registry = er.async_get(hass)
    ports = {
        e.unique_id
        for e in er.async_entries_for_config_entry(registry, config_entry.entry_id)
        if e.entity_id.startswith("binary_sensor.bbox_ethernet_port")
    }
    assert ports == {
        f"{BOX_ID}-led.ethernetPort.0.state",
        f"{BOX_ID}-led.ethernetPort.1.state",
    }
    assert registry.async_get("binary_sensor.bbox_ethernet_port_3") is None


async def test_ethernet_ports_looked_up_by_id(
    hass: HomeAssistant, config_entry: ConfigEntry, router: FakeBox
) -> None:
    """The state is found by port id, not by position, and ports can appear later."""
    router.route("device/led", status=500)
    await setup_entry(hass, config_entry)
    registry = er.async_get(hass)
    assert registry.async_get("binary_sensor.bbox_ethernet_port_7") is None

    # derived variant (anonymous): ids 7 and 9, the answer comes after the setup
    router.route(
        "device/led",
        [{"ethernetPort": [{"id": 7, "state": "Up"}, {"id": 9, "state": "Down"}]}],
    )
    await config_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    entity = registry.async_get("binary_sensor.bbox_ethernet_port_7")
    assert entity is not None
    assert entity.disabled_by is not None  # disabled by default
    assert registry.async_get("binary_sensor.bbox_ethernet_port_9") is not None
    # a second update does not create duplicates
    await config_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert len(_port_entities(registry, config_entry)) == 2

    for port in (7, 9):
        registry.async_update_entity(
            f"binary_sensor.bbox_ethernet_port_{port}", disabled_by=None
        )
    await hass.config_entries.async_reload(config_entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.bbox_ethernet_port_7").state == STATE_ON
    assert hass.states.get("binary_sensor.bbox_ethernet_port_9").state == STATE_OFF

    # port 7 disappears from the answer: its state is unknown
    router.route("device/led", [{"ethernetPort": [{"id": 9, "state": "Up"}]}])
    await config_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.bbox_ethernet_port_7").state == STATE_UNKNOWN


async def test_malformed_ports_are_ignored(
    hass: HomeAssistant, config_entry: ConfigEntry, router: FakeBox
) -> None:
    """A list of ports which is not one gives no port sensor."""
    router.route("device/led", [{"ethernetPort": "none"}])
    await setup_entry(hass, config_entry)
    registry = er.async_get(hass)
    assert _port_entities(registry, config_entry) == []
