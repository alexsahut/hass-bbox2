"""Config flow for Bouygues Bbox integration."""

from __future__ import annotations

import ipaddress
import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_VERIFY_SSL
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import (
    BboxAuthError,
    BboxClient,
    BboxConnectionError,
    BboxDnsError,
    BboxError,
    BboxNotFoundError,
    BboxRedirectError,
    BboxResponseError,
)
from .const import (
    CONF_REFRESH_RATE,
    CONF_TRACK_DEVICES,
    CONF_USE_TLS,
    DEFAULT_HOST,
    DEFAULT_REFRESH_RATE,
    DEFAULT_TITLE,
    DEFAULT_TRACK_DEVICES,
    DEFAULT_USE_TLS,
    DEFAULT_VERIFY_SSL,
    DOMAIN,
)
from .helpers import box_identifier

_LOGGER = logging.getLogger(__name__)


def _is_ip_address(host: str) -> bool:
    """Return True if the host is an IP address."""
    try:
        ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return False
    return True


PASSWORD_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))

SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST, default=DEFAULT_HOST): str,
        vol.Optional(CONF_PASSWORD, default=""): PASSWORD_SELECTOR,
        vol.Required(CONF_USE_TLS, default=DEFAULT_USE_TLS): bool,
        vol.Required(CONF_VERIFY_SSL, default=DEFAULT_VERIFY_SSL): bool,
    }
)


CONF_REMOVE_PASSWORD = "remove_password"


def _reconfigure_schema(has_password: bool) -> vol.Schema:
    """Return the reconfigure schema.

    The current password is never sent back to the form: an empty field keeps
    it, a new value replaces it, the checkbox (shown only when a password is
    set) removes it.
    """
    schema: dict[Any, Any] = {
        vol.Required(CONF_HOST): str,
        vol.Optional(CONF_PASSWORD, default=""): PASSWORD_SELECTOR,
    }
    if has_password:
        schema[vol.Optional(CONF_REMOVE_PASSWORD, default=False)] = bool
    schema[vol.Required(CONF_USE_TLS)] = bool
    schema[vol.Required(CONF_VERIFY_SSL)] = bool
    return vol.Schema(schema)


def _normalize(user_input: Mapping[str, Any]) -> dict[str, Any]:
    """Return the connection data: host stripped, no SSL verification on an IP."""
    data = {
        CONF_HOST: user_input[CONF_HOST].strip(),
        CONF_PASSWORD: user_input.get(CONF_PASSWORD) or "",
        CONF_USE_TLS: user_input[CONF_USE_TLS],
        CONF_VERIFY_SSL: user_input[CONF_VERIFY_SSL],
    }
    if data[CONF_VERIFY_SSL] and _is_ip_address(data[CONF_HOST]):
        # The Bbox certificate is issued for a hostname, not for an IP address
        _LOGGER.debug("Host is an IP address, SSL verification is disabled")
        data[CONF_VERIFY_SSL] = False
    return data


def _error_key(error: BboxError) -> str:
    """Return the form error matching an API client error."""
    if isinstance(error, BboxRedirectError):
        return "redirect"
    if isinstance(error, BboxDnsError):
        return "dns_error"
    if isinstance(error, BboxAuthError):
        return "invalid_auth"
    if isinstance(error, BboxConnectionError):
        return "cannot_connect"
    if isinstance(error, BboxNotFoundError | BboxResponseError):
        return "invalid_response"
    return "unknown"


async def _async_identify(hass: HomeAssistant, data: Mapping[str, Any]) -> str | None:
    """Check the connection and return the identifier of the box.

    The identifier is the LAN MAC address (`lan/ip`, public): the same with or
    without password. With a password, the login checks it first. Raises a
    BboxError when the box can not be read.
    """
    client = BboxClient(
        async_get_clientsession(hass, verify_ssl=data[CONF_VERIFY_SSL]),
        data[CONF_HOST],
        password=data.get(CONF_PASSWORD) or None,
        use_tls=data[CONF_USE_TLS],
    )
    if client.has_password:
        await client.async_login()
    return box_identifier(await client.async_get("lan/ip"))


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Bouygues Bbox."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Create the options flow."""
        return OptionsFlow()

    async def async_step_user(
        self, user_input: Mapping[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input:
            user_input = _normalize(user_input)
            try:
                box_id = await _async_identify(self.hass, user_input)
            except BboxError as err:
                errors["base"] = _error_key(err)
                _LOGGER.warning("Unable to set up the Bbox: %s", err)
            else:
                if not box_id:
                    errors["base"] = "no_identifier"
                else:
                    await self.async_set_unique_id(box_id)
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(title=DEFAULT_TITLE, data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(SCHEMA, user_input),
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Perform reauthentication upon an API authentication error."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm reauthentication dialog. The password is optional."""
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            password = user_input.get(CONF_PASSWORD) or ""
            try:
                box_id = await _async_identify(
                    self.hass, {**entry.data, CONF_PASSWORD: password}
                )
            except BboxError as err:
                errors["base"] = _error_key(err)
                _LOGGER.warning("Unable to reauthenticate to the Bbox: %s", err)
            else:
                if not box_id:
                    errors["base"] = "no_identifier"
                elif box_id != entry.unique_id:
                    return self.async_abort(reason="wrong_account")
                else:
                    # The identifier does not depend on the password: unchanged
                    return self.async_update_reload_and_abort(
                        entry, data_updates={CONF_PASSWORD: password}
                    )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {vol.Optional(CONF_PASSWORD, default=""): PASSWORD_SELECTOR}
            ),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: Mapping[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change the connection (host, TLS, certificate) and the password.

        The box read must be the one of the entry (same LAN MAC address), so
        the unique_ids of the entry and of its entities are kept.
        """
        errors: dict[str, str] = {}
        entry = self._get_reconfigure_entry()
        has_password = bool(entry.data.get(CONF_PASSWORD))
        if user_input is not None:
            remove = user_input.get(CONF_REMOVE_PASSWORD, False)
            new_password = user_input.get(CONF_PASSWORD) or ""
            if remove and new_password:
                errors["base"] = "password_and_remove"
            else:
                if remove:
                    password = ""
                else:
                    password = new_password or entry.data.get(CONF_PASSWORD) or ""
                data = _normalize({**user_input, CONF_PASSWORD: password})
                try:
                    box_id = await _async_identify(self.hass, data)
                except BboxError as err:
                    errors["base"] = _error_key(err)
                    _LOGGER.warning("Unable to reconfigure the Bbox: %s", err)
                else:
                    if not box_id:
                        errors["base"] = "no_identifier"
                    elif box_id != entry.unique_id:
                        return self.async_abort(reason="wrong_account")
                    else:
                        return self.async_update_reload_and_abort(
                            entry, data_updates=data
                        )

        suggested = {
            k: v
            for k, v in (user_input or entry.data).items()
            if k not in (CONF_PASSWORD, CONF_REMOVE_PASSWORD)
        }
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                _reconfigure_schema(has_password), suggested
            ),
            errors=errors,
        )


class OptionsFlow(config_entries.OptionsFlow):
    """Handle a options flow for Bouygues Bbox."""

    async def async_step_init(
        self, user_input: Mapping[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input:
            return self.async_create_entry(data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(
                    {
                        vol.Optional(
                            CONF_REFRESH_RATE, default=DEFAULT_REFRESH_RATE
                        ): int,
                        vol.Optional(
                            CONF_TRACK_DEVICES, default=DEFAULT_TRACK_DEVICES
                        ): bool,
                    }
                ),
                self.config_entry.options,
            ),
        )
