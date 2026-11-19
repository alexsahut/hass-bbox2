"""The tests for the bbox component."""

from unittest.mock import AsyncMock, patch

import pytest
from bboxpy.exceptions import BboxException
from homeassistant.components.button import DOMAIN as BUTTON_DOMAIN
from homeassistant.components.button import SERVICE_PRESS
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant


async def test_refresh(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    router,
) -> None:
    """Pressing refresh requests a coordinator refresh."""
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    with patch.object(
        config_entry.runtime_data, "async_request_refresh", AsyncMock()
    ) as refresh:
        await hass.services.async_call(
            BUTTON_DOMAIN,
            SERVICE_PRESS,
            {ATTR_ENTITY_ID: "button.bbox_refresh"},
            blocking=True,
        )
    refresh.assert_awaited_once()


async def test_no_restart_button(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    router,
) -> None:
    """The restart button does not exist anymore."""
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get("button.bbox_restart") is None
    assert not hass.states.async_entity_ids("switch")


async def test_refresh_error_is_logged(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    router,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A BboxException on refresh is logged, not raised."""
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    with patch.object(
        config_entry.runtime_data,
        "async_request_refresh",
        AsyncMock(side_effect=BboxException("boom")),
    ):
        await hass.services.async_call(
            BUTTON_DOMAIN,
            SERVICE_PRESS,
            {ATTR_ENTITY_ID: "button.bbox_refresh"},
            blocking=True,
        )
    assert "boom" in caplog.text
