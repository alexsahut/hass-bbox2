"""Tests of the setup of the config entry."""

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .common import setup_entry
from .conftest import FakeBox


async def test_setup_entry(
    hass: HomeAssistant, config_entry: ConfigEntry, router: FakeBox
) -> None:
    """Setup with a password reads the public and the authenticated endpoints."""
    await setup_entry(hass, config_entry)

    assert config_entry.state == ConfigEntryState.LOADED
    assert router.count("login", "POST") == 1
    assert router.endpoints >= {
        "device",
        "device/cpu",
        "device/mem",
        "device/led",
        "wan/ip",
        "wan/ip/stats",
        "summary",
        "wireless/wps",
        "hosts",
        "wireless",
        "speedtest/info",
        "device/summary",
    }
    # parentalcontrol is not read anymore
    assert not any("parentalcontrol" in endpoint for endpoint in router.endpoints)
    assert hass.states.get("button.bbox_refresh") is not None


async def test_setup_entry_without_password(
    hass: HomeAssistant, public_config_entry: ConfigEntry, public_router: FakeBox
) -> None:
    """Without password: public endpoints only, no login, no authenticated call."""
    await setup_entry(hass, public_config_entry)
    await public_config_entry.runtime_data.async_refresh()

    assert public_config_entry.state == ConfigEntryState.LOADED
    assert public_router.requests
    assert all(method == "GET" for method, _ in public_router.requests)
    assert public_router.endpoints == {
        "device",
        "device/cpu",
        "device/mem",
        "device/led",
        "wan/ip",
        "wan/ip/stats",
        "summary",
        "wireless/wps",
    }
    assert not hass.states.async_entity_ids("device_tracker")
    assert hass.states.get("sensor.bbox_ip_address").state == "203.0.113.46"


async def test_track_devices_option(
    hass: HomeAssistant, config_entry: ConfigEntry, router: FakeBox
) -> None:
    """The device trackers are not created when the option is disabled."""
    hass.config_entries.async_update_entry(
        config_entry, options={"track_devices": False}
    )
    await setup_entry(hass, config_entry)

    assert config_entry.state == ConfigEntryState.LOADED
    registry = er.async_get(hass)
    assert not [
        e
        for e in er.async_entries_for_config_entry(registry, config_entry.entry_id)
        if e.domain == "device_tracker"
    ]


async def test_box_device_is_registered(
    hass: HomeAssistant, config_entry: ConfigEntry, router: FakeBox
) -> None:
    """The Bbox is a device of the entry (parent of the connected hosts)."""
    await setup_entry(hass, config_entry)

    registry = dr.async_get(hass)
    devices = dr.async_entries_for_config_entry(registry, config_entry.entry_id)
    box = next(d for d in devices if d.via_device_id is None)
    assert box.model == "F@st5696b"
    assert box.sw_version == "25.5.76"
    assert all(d.via_device_id == box.id for d in devices if d is not box)


async def test_setup_without_the_device_endpoint(
    hass: HomeAssistant, config_entry: ConfigEntry, router: FakeBox
) -> None:
    """The entry loads even if `device` is not readable (no model, no version)."""
    router.route("device", status=500)
    await setup_entry(hass, config_entry)

    assert config_entry.state == ConfigEntryState.LOADED
    registry = dr.async_get(hass)
    box = dr.async_entries_for_config_entry(registry, config_entry.entry_id)[0]
    assert box.model is None


async def test_write_entities_are_removed_from_registry(
    hass: HomeAssistant, config_entry: ConfigEntry, router: FakeBox
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

    await setup_entry(hass, config_entry)
    assert all(registry.async_get(e) is None for e in old)
    assert all(registry.async_get(e) is not None for e in kept)

    # Idempotent: a second load with nothing to remove raises nothing.
    assert await hass.config_entries.async_reload(config_entry.entry_id)
    assert config_entry.state == ConfigEntryState.LOADED
    assert all(registry.async_get(e) is not None for e in kept)


async def test_unload(
    hass: HomeAssistant, config_entry: ConfigEntry, router: FakeBox
) -> None:
    """Unloading the entry needs no session cleanup (the session is Home Assistant's)."""
    await setup_entry(hass, config_entry)
    assert await hass.config_entries.async_unload(config_entry.entry_id)
    assert config_entry.state == ConfigEntryState.NOT_LOADED
