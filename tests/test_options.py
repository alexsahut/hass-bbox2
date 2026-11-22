"""Tests of the options (refresh rate, devices to track) and of the migration."""

from typing import Any

import pytest
import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.bbox.config_flow import ConfigFlow
from custom_components.bbox.const import DOMAIN

from .common import setup_entry
from .conftest import FakeBox
from .const import BOX_ID, MOCK_USER_INPUT, SYNTHETIC_HOSTS

MAC_1 = "00:01:02:03:04:0e"
MAC_4 = "01:02:03:04:05:f9"
MAC_6 = "01:02:03:04:05:06"


def selector_options(result: dict[str, Any]) -> dict[str, str]:
    """The (MAC -> label) options of the devices selector."""
    key = next(k for k in result["data_schema"].schema if k == "tracked_devices")
    config = result["data_schema"].schema[key].config
    assert config["multiple"] is True
    assert config["mode"] == "dropdown"
    return {o["value"]: o["label"] for o in config["options"]}


async def test_options_with_the_hosts(
    hass: HomeAssistant, config_entry: ConfigEntry, router: FakeBox
) -> None:
    """Loaded entry with a password: refresh rate and devices to track."""
    await setup_entry(hass, config_entry)

    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "init"
    defaults = {str(k): k.default() for k in result["data_schema"].schema if k.default}
    # nothing tracked by default
    assert defaults == {"refresh_rate": 60, "tracked_devices": []}
    # active first (Host-001, Host-004), then Host-006; English (language of hass)
    assert list(selector_options(result).items()) == [
        (MAC_1, "Host-001 — online, Ethernet"),
        (MAC_4, "Host-004 — online, Wi-Fi 5 GHz"),
        (MAC_6, "Host-006 — offline, Wi-Fi 2.4 GHz"),
    ]

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"refresh_rate": 120, "tracked_devices": [MAC_4, MAC_4]}
    )
    await hass.async_block_till_done()
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert config_entry.options == {"refresh_rate": 120, "tracked_devices": [MAC_4]}
    # the entry was reloaded: the chosen device has its tracker
    assert hass.states.get("device_tracker.host_004") is not None
    assert hass.states.get("device_tracker.host_001") is None


async def test_options_labels_in_french(
    hass: HomeAssistant, config_entry: ConfigEntry, router: FakeBox
) -> None:
    """The labels follow the language of Home Assistant (French or English)."""
    hass.config.language = "fr"
    await setup_entry(hass, config_entry)

    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    assert selector_options(result)[MAC_6] == "Host-006 — hors ligne, Wi-Fi 2.4 GHz"
    assert selector_options(result)[MAC_1].endswith("en ligne, Ethernet")


@pytest.mark.parametrize("options", [{"tracked_devices": ["02:00:00:00:00:FF", MAC_1]}])
async def test_options_keep_a_mac_not_listed(
    hass: HomeAssistant, config_entry: ConfigEntry, router: FakeBox
) -> None:
    """A chosen MAC which the box does not list stays proposed (and selected)."""
    router.route("hosts", SYNTHETIC_HOSTS)
    await setup_entry(hass, config_entry)

    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    options = selector_options(result)
    assert options["02:00:00:00:00:FF"] == "Unknown device (00FF)"
    assert "02:00:00:00:00:02" in options
    # the unknown device is accepted, so saving the options does not lose it
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "refresh_rate": 60,
            "tracked_devices": ["02:00:00:00:00:FF", "02:00:00:00:00:02"],
        },
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert config_entry.options["tracked_devices"] == [
        "02:00:00:00:00:FF",
        "02:00:00:00:00:02",
    ]


async def test_options_reject_an_unknown_choice(
    hass: HomeAssistant, config_entry: ConfigEntry, router: FakeBox
) -> None:
    """Only the proposed devices can be chosen."""
    await setup_entry(hass, config_entry)
    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    with pytest.raises(vol.Invalid):
        await hass.config_entries.options.async_configure(
            result["flow_id"], {"refresh_rate": 60, "tracked_devices": ["02:aa"]}
        )


async def test_options_without_password(
    hass: HomeAssistant, public_config_entry: ConfigEntry, public_router: FakeBox
) -> None:
    """No hosts without password: refresh rate only, the choice is kept."""
    hass.config_entries.async_update_entry(
        public_config_entry, options={"tracked_devices": [MAC_1]}
    )
    await setup_entry(hass, public_config_entry)

    result = await hass.config_entries.options.async_init(public_config_entry.entry_id)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "init_no_devices"
    assert [str(k) for k in result["data_schema"].schema] == ["refresh_rate"]

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"refresh_rate": 90}
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert public_config_entry.options == {
        "refresh_rate": 90,
        "tracked_devices": [MAC_1],
    }


async def test_options_with_an_entry_not_loaded(
    hass: HomeAssistant, router: FakeBox
) -> None:
    """An entry which is not loaded has no hosts: refresh rate only."""
    entry = MockConfigEntry(domain=DOMAIN, unique_id=BOX_ID, data=MOCK_USER_INPUT)
    entry.add_to_hass(hass)
    assert entry.state is ConfigEntryState.NOT_LOADED

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["step_id"] == "init_no_devices"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"refresh_rate": 120}
    )
    assert entry.options == {"refresh_rate": 120}


async def test_options_with_no_host_listed(
    hass: HomeAssistant, config_entry: ConfigEntry, router: FakeBox
) -> None:
    """The box listed no host and nothing is chosen: nothing to select."""
    router.route("hosts", [{"hosts": {"list": []}}])
    await setup_entry(hass, config_entry)
    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    assert result["step_id"] == "init_no_devices"


# --- migration ---------------------------------------------------------------


@pytest.mark.parametrize("track", [True, False])
async def test_migration_of_track_devices(
    hass: HomeAssistant, router: FakeBox, track: bool
) -> None:
    """2.0.1 `track_devices` (true or false) becomes `tracked_devices: []`."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=BOX_ID,
        data=MOCK_USER_INPUT,
        options={"refresh_rate": 30, "track_devices": track},
        entry_id="123456",
    )
    entry.add_to_hass(hass)
    assert (entry.version, entry.minor_version) == (1, 1)
    registry = er.async_get(hass)
    registry.async_get_or_create("device_tracker", DOMAIN, MAC_1, config_entry=entry)

    await setup_entry(hass, entry)

    assert entry.state is ConfigEntryState.LOADED
    assert entry.options == {"refresh_rate": 30, "tracked_devices": []}
    # the major version is unchanged: 2.0.1 can still load the entry
    assert (entry.version, entry.minor_version) == (1, ConfigFlow.MINOR_VERSION)
    assert ConfigFlow.VERSION == 1
    # nothing is recreated, the former trackers are removed
    assert not [
        e
        for e in er.async_entries_for_config_entry(registry, entry.entry_id)
        if e.domain == "device_tracker"
    ]


async def test_migration_without_the_option(
    hass: HomeAssistant, router: FakeBox
) -> None:
    """An entry which never had the option gets an empty list; a list is kept."""
    entry = MockConfigEntry(domain=DOMAIN, unique_id=BOX_ID, data=MOCK_USER_INPUT)
    entry.add_to_hass(hass)
    await setup_entry(hass, entry)
    assert entry.options == {"tracked_devices": []}


async def test_migrated_entry_is_not_migrated_again(
    hass: HomeAssistant, router: FakeBox
) -> None:
    """Minor version 2: the options are not touched at the next loads."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=BOX_ID,
        data=MOCK_USER_INPUT,
        options={"tracked_devices": [MAC_1]},
        minor_version=2,
    )
    entry.add_to_hass(hass)
    await setup_entry(hass, entry)
    assert entry.options == {"tracked_devices": [MAC_1]}


async def test_entry_of_a_newer_major_version_is_refused(
    hass: HomeAssistant, router: FakeBox
) -> None:
    """A major version above ours is not loaded (Home Assistant refuses it)."""
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=BOX_ID, data=MOCK_USER_INPUT, version=2
    )
    entry.add_to_hass(hass)
    await setup_entry(hass, entry)
    assert entry.state is ConfigEntryState.MIGRATION_ERROR
