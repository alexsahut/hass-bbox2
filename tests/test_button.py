"""The tests for the bbox refresh button."""

from homeassistant.components.button import DOMAIN as BUTTON_DOMAIN
from homeassistant.components.button import SERVICE_PRESS
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_ENTITY_ID, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant

from .common import setup_entry
from .conftest import FakeBox


async def test_refresh(
    hass: HomeAssistant, config_entry: ConfigEntry, router: FakeBox
) -> None:
    """Pressing refresh reads the box again (GET only)."""
    await setup_entry(hass, config_entry)
    before = router.count("device/mem")

    await hass.services.async_call(
        BUTTON_DOMAIN,
        SERVICE_PRESS,
        {ATTR_ENTITY_ID: "button.bbox_refresh"},
        blocking=True,
    )
    await hass.async_block_till_done()

    assert router.count("device/mem") == before + 1


async def test_no_restart_button(
    hass: HomeAssistant, config_entry: ConfigEntry, router: FakeBox
) -> None:
    """The restart button does not exist anymore."""
    await setup_entry(hass, config_entry)

    assert hass.states.get("button.bbox_restart") is None
    assert not hass.states.async_entity_ids("switch")


async def test_refresh_button_stays_available_when_an_endpoint_fails(
    hass: HomeAssistant, config_entry: ConfigEntry, router: FakeBox
) -> None:
    """The button does not depend on any endpoint."""
    router.route("device", status=500)
    await setup_entry(hass, config_entry)
    state = hass.states.get("button.bbox_refresh")
    assert state is not None
    assert state.state != STATE_UNAVAILABLE
