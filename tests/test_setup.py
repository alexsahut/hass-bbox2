"""Tests pour l'intégration Bbox2 utilisant config_entries."""

from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.components.sensor import SensorEntityDescription
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.bbox.device_tracker import BboxDeviceTracker


@pytest.mark.asyncio
async def test_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    router: Generator[AsyncMock | MagicMock],
) -> None:
    """Test du setup via une config entry."""

    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert config_entry.state == ConfigEntryState.LOADED


@pytest.mark.asyncio
async def test_track_devices_option(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    router: Generator[AsyncMock | MagicMock],
) -> None:
    """Test the device trackers are not created when the option is disabled."""
    hass.config_entries.async_update_entry(
        config_entry, options={"track_devices": False}
    )
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert config_entry.state == ConfigEntryState.LOADED
    assert not hass.states.async_entity_ids("device_tracker")


@pytest.mark.asyncio
async def test_connected_devices_are_linked_to_the_box(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    router: Generator[AsyncMock | MagicMock],
) -> None:
    """Test the connected devices use via_device_id to reference the Bbox."""
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    registry = dr.async_get(hass)
    devices = dr.async_entries_for_config_entry(registry, config_entry.entry_id)
    assert len(devices) == 1
    box = devices[0]
    assert box.via_device_id is None

    # The device trackers describe the hosts as children of the Bbox device.
    coordinator = config_entry.runtime_data
    hosts = coordinator.data["devices"]["hosts"]["list"]
    tracker = BboxDeviceTracker(
        coordinator, SensorEntityDescription(key="tracker"), hosts[0]
    )
    assert tracker._attr_device_info["via_device_id"] == box.id


@pytest.mark.asyncio
async def test_write_entities_are_removed_from_registry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    router: Generator[AsyncMock | MagicMock],
) -> None:
    """Switch and restart entities of this entry are removed, others are kept."""
    other_entry = MockConfigEntry(domain="other", entry_id="other_entry")
    other_entry.add_to_hass(hass)
    registry = er.async_get(hass)

    def create(domain, platform, unique_id, entry):
        return registry.async_get_or_create(
            domain, platform, unique_id, config_entry=entry
        ).entity_id

    old = [
        create("switch", "bbox", "box-wifi", config_entry),
        create("switch", "bbox", "box_aa_bb_parental_control", config_entry),
        create("button", "bbox", "box-restart", config_entry),
    ]
    kept = [
        create("button", "bbox", "box-refresh", config_entry),
        create("sensor", "bbox", "box-something", config_entry),
        create("switch", "other", "box-wifi", other_entry),
        create("button", "other", "box-restart", other_entry),
    ]

    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert all(registry.async_get(e) is None for e in old)
    assert all(registry.async_get(e) is not None for e in kept)

    # Idempotent: a second load with nothing to remove raises nothing.
    assert await hass.config_entries.async_reload(config_entry.entry_id)
    assert config_entry.state == ConfigEntryState.LOADED
    assert all(registry.async_get(e) is not None for e in kept)
