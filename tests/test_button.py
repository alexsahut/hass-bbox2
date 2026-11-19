"""The tests for the bbox component."""

from unittest.mock import AsyncMock, patch

import pytest
from bboxpy.exceptions import BboxException
from homeassistant.components.button import DOMAIN as BUTTON_DOMAIN
from homeassistant.components.button import SERVICE_PRESS
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from syrupy.assertion import SnapshotAssertion


async def test_reboot(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    entity_registry: er.EntityRegistry,
    snapshot: SnapshotAssertion,
    router,
) -> None:
    """Test reboot button."""

    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    data = {
        ATTR_ENTITY_ID: "button.bbox_restart",
    }

    await hass.services.async_call(
        BUTTON_DOMAIN,
        SERVICE_PRESS,
        service_data=data,
        blocking=True,
    )
    await hass.async_block_till_done()


async def test_reboot_calls_box(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    router,
) -> None:
    """Pressing restart calls the reboot API."""
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    await hass.services.async_call(
        BUTTON_DOMAIN,
        SERVICE_PRESS,
        {ATTR_ENTITY_ID: "button.bbox_restart"},
        blocking=True,
    )
    router.return_value.device.async_reboot.assert_awaited_once()


async def test_reboot_error_is_logged(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    router,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A BboxException on reboot is logged, not raised."""
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    router.return_value.device.async_reboot.side_effect = BboxException("boom")

    await hass.services.async_call(
        BUTTON_DOMAIN,
        SERVICE_PRESS,
        {ATTR_ENTITY_ID: "button.bbox_restart"},
        blocking=True,
    )
    assert "boom" in caplog.text


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
