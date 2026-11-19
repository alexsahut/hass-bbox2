"""Tests for the Bbox binary sensor platform."""

import copy

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .common import setup_entry
from .conftest import FakeBox
from .const import DEVICE_WITH_SERIAL


async def test_binary_sensor_link_status(
    hass: HomeAssistant, config_entry: ConfigEntry, router: FakeBox
) -> None:
    """The link status follows device.status (value rules belong to S3)."""
    await setup_entry(hass, config_entry)
    assert hass.states.get("binary_sensor.bbox_link_status").state == STATE_ON

    device = copy.deepcopy(DEVICE_WITH_SERIAL)
    device[0]["device"]["status"] = 0
    router.route("device", device)
    await config_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    assert hass.states.get("binary_sensor.bbox_link_status").state == STATE_OFF


async def test_ethernet_ports(
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
    router.route("device/led", status=500)
    await setup_entry(hass, config_entry)
    registry = er.async_get(hass)
    entity = registry.async_get("binary_sensor.bbox_ethernet_port_1")
    registry.async_update_entity(entity.entity_id, disabled_by=None)
    await hass.config_entries.async_reload(config_entry.entry_id)
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


async def test_missing_ethernet_port_has_no_value(
    hass: HomeAssistant, config_entry: ConfigEntry, router: FakeBox
) -> None:
    """A box reporting fewer ports than the sensors gives an unknown state."""
    router.route("device/led", [{"ethernetPort": [{"id": 1, "state": "Up"}]}])
    await setup_entry(hass, config_entry)
    registry = er.async_get(hass)
    registry.async_update_entity("binary_sensor.bbox_ethernet_port_2", disabled_by=None)
    await hass.config_entries.async_reload(config_entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get("binary_sensor.bbox_ethernet_port_2").state == STATE_UNKNOWN
