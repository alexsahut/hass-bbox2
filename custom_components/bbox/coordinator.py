"""Coordinator for Bbox."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_VERIFY_SSL
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    BboxClient,
    BboxError,
    BboxLoginError,
    BboxNotFoundError,
    BboxResponseError,
)
from .const import (
    CONF_REFRESH_RATE,
    CONF_USE_TLS,
    DEFAULT_REFRESH_RATE,
    DEFAULT_USE_TLS,
    DEFAULT_VERIFY_SSL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

MAX_CONCURRENT_REQUESTS = 4


@dataclass(frozen=True)
class Endpoint:
    """An endpoint read at each refresh, stored in the data under ``key``."""

    key: str
    path: str


# Public endpoints, read with or without password.
PUBLIC_ENDPOINTS: tuple[Endpoint, ...] = (
    Endpoint("info", "device"),
    Endpoint("cpu", "device/cpu"),
    Endpoint("memory", "device/mem"),
    Endpoint("led", "device/led"),
    Endpoint("wan_ip", "wan/ip"),
    Endpoint("wan_ip_stats", "wan/ip/stats"),
    Endpoint("summary", "summary"),
    Endpoint("wps", "wireless/wps"),
    Endpoint("upnp_igd", "upnp/igd"),
    Endpoint("wan_ftth_stats", "wan/ftth/stats"),
    Endpoint("wan_diags", "wan/diags"),
    Endpoint("lan_stats", "lan/stats"),
    Endpoint("alerts", "alerts"),
    Endpoint("lan_ip", "lan/ip"),
)

# Endpoints which require a password: read only when one is configured.
AUTHENTICATED_ENDPOINTS: tuple[Endpoint, ...] = (
    Endpoint("devices", "hosts"),
    Endpoint("wifi", "wireless"),
    Endpoint("speedtest_infos", "speedtest/info"),
    Endpoint("device_summary", "device/summary"),
)


def _normalize(key: str, payload: Any) -> dict[str, Any]:
    """Return the content of an answer as a dict.

    The Bbox wraps its answers in a list with one element. The hosts may be split
    in several elements, in this case their lists are concatenated.
    """
    if isinstance(payload, dict):
        return payload
    if (
        isinstance(payload, list)
        and payload
        and all(isinstance(item, dict) for item in payload)
    ):
        if len(payload) == 1:
            return payload[0]
        if key == "devices":
            hosts = [
                h for item in payload for h in item.get("hosts", {}).get("list", [])
            ]
            return {"hosts": {"list": hosts}}
    raise BboxResponseError(f"Unexpected content for {key}")


class BboxDataUpdateCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """Fetch the data of the Bbox, endpoint by endpoint."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator and its API client."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(
                seconds=entry.options.get(CONF_REFRESH_RATE, DEFAULT_REFRESH_RATE)
            ),
        )
        self.client = BboxClient(
            async_get_clientsession(
                hass, verify_ssl=entry.data.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL)
            ),
            entry.data[CONF_HOST],
            password=entry.data.get(CONF_PASSWORD) or None,
            use_tls=entry.data.get(CONF_USE_TLS, DEFAULT_USE_TLS),
        )
        self._unsupported: set[str] = set()
        self._failing: set[str] = set()

    @property
    def box_id(self) -> str:
        """Return the identifier of the box (LAN MAC address, see config flow)."""
        return str(self.config_entry.unique_id)

    @property
    def has_password(self) -> bool:
        """Return True if a password is configured."""
        return self.client.has_password

    @property
    def endpoints(self) -> tuple[Endpoint, ...]:
        """Return the endpoints read with the current configuration."""
        if self.has_password:
            return PUBLIC_ENDPOINTS + AUTHENTICATED_ENDPOINTS
        return PUBLIC_ENDPOINTS

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        """Fetch the data. An endpoint in error only removes its own data."""
        endpoints = [e for e in self.endpoints if e.path not in self._unsupported]
        if not endpoints:
            raise UpdateFailed("None of the endpoints is available on this Bbox")

        # The first request alone: it opens the session when there is a password,
        # so that a refused login is not repeated by the concurrent requests.
        first = await self._async_fetch(endpoints[0])
        if isinstance(first, BboxLoginError):
            raise ConfigEntryAuthFailed(
                f"Login refused by {self.client.host}"
            ) from first
        outcomes = [first]
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

        async def fetch(endpoint: Endpoint) -> Any:
            async with semaphore:
                return await self._async_fetch(endpoint)

        outcomes += await asyncio.gather(*(fetch(e) for e in endpoints[1:]))

        data: dict[str, dict[str, Any]] = {}
        last_error: BboxError | None = None
        for endpoint, outcome in zip(endpoints, outcomes, strict=True):
            if isinstance(outcome, BboxLoginError):
                raise ConfigEntryAuthFailed(
                    f"Login refused by {self.client.host}"
                ) from outcome
            if isinstance(outcome, BboxError):
                last_error = outcome
                self._handle_error(endpoint, outcome)
                continue
            self._handle_success(endpoint)
            data[endpoint.key] = outcome

        if not data:
            raise UpdateFailed(f"No endpoint answered: {last_error}") from last_error
        return data

    async def _async_fetch(self, endpoint: Endpoint) -> dict[str, Any] | BboxError:
        """Read one endpoint, return the error instead of raising it."""
        try:
            payload = await self.client.async_get(
                endpoint.path,
                authenticated=endpoint in AUTHENTICATED_ENDPOINTS,
            )
            return _normalize(endpoint.key, payload)
        except BboxError as err:
            return err

    def _handle_error(self, endpoint: Endpoint, error: BboxError) -> None:
        """Log an endpoint error once, and stop requesting a missing endpoint."""
        if isinstance(error, BboxNotFoundError):
            self._unsupported.add(endpoint.path)
            _LOGGER.info(
                "%s is not available on this Bbox, it will not be requested anymore",
                endpoint.path,
            )
        elif endpoint.path not in self._failing:
            self._failing.add(endpoint.path)
            _LOGGER.warning("Unable to read %s: %s", endpoint.path, error)
        else:
            _LOGGER.debug("Unable to read %s: %s", endpoint.path, error)

    def _handle_success(self, endpoint: Endpoint) -> None:
        if endpoint.path in self._failing:
            self._failing.discard(endpoint.path)
            _LOGGER.info("%s is available again", endpoint.path)
