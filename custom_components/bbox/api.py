"""Minimal read-only client for the Bbox web API.

The client only issues ``GET`` requests. The single exception is the ``POST`` of
the login, which is needed to open an authenticated session. There is no method
able to modify the box, and ``_request`` refuses anything else.
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
import socket
from dataclasses import dataclass, field
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

API_PATH = "/api/v1/"
LOGIN_ENDPOINT = "login"
TOKEN_ENDPOINT = "device/token"
REQUEST_TIMEOUT = 10


class BboxError(Exception):
    """Base class of the errors raised by the client."""


class BboxConnectionError(BboxError):
    """The box can not be reached (refused, unreachable, timeout, TLS...)."""


class BboxDnsError(BboxConnectionError):
    """The host name can not be resolved."""


class BboxRedirectError(BboxError):
    """The box answered with a redirect (typical when it is queried by its IP)."""

    def __init__(self, message: str, location: str | None = None) -> None:
        """Initialize with the redirect target, when known."""
        super().__init__(message)
        self.location = location


class BboxAuthError(BboxError):
    """The box answered 401/403: the request needs an authenticated session."""


class BboxLoginError(BboxAuthError):
    """The login has been refused (wrong password) or could not be performed."""


class BboxNotFoundError(BboxError):
    """The endpoint does not exist on this box (HTTP 404)."""


class BboxResponseError(BboxError):
    """The answer is not a valid Bbox API response."""


@dataclass(frozen=True)
class _Response:
    """What is kept from an HTTP response."""

    status: int
    text: str
    location: str | None = None
    cookies: dict[str, str] = field(default_factory=dict)


def _is_ip_address(host: str) -> bool:
    try:
        ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return False
    return True


class BboxClient:
    """Client of the Bbox API, read-only.

    Without password only the public endpoints can be read. With a password, the
    client opens a session before the first request and opens a new one, once,
    when the box answers 401 (expired session).
    """

    def __init__(
        self,
        session: aiohttp.ClientSession,
        host: str,
        *,
        password: str | None = None,
        use_tls: bool = True,
    ) -> None:
        """Initialize the client with a session provided by Home Assistant."""
        self._session = session
        self._host = host
        netloc = f"[{host}]" if _is_ip_address(host) and ":" in host else host
        self._base_url = f"{'https' if use_tls else 'http'}://{netloc}{API_PATH}"
        self._password = password or None
        self._cookies: dict[str, str] = {}
        self._token: str | None = None
        self._logged_in = False
        self._login_generation = 0
        self._login_lock = asyncio.Lock()

    @property
    def host(self) -> str:
        """Return the host name (or IP address) of the box."""
        return self._host

    @property
    def has_password(self) -> bool:
        """Return True if a password is configured."""
        return self._password is not None

    async def async_login(self) -> None:
        """Open a session with the password (the only POST of the client)."""
        if self._password is None:
            raise BboxLoginError("No password configured")
        await self._async_login(self._login_generation, force=True)

    async def async_get(self, endpoint: str, *, authenticated: bool = False) -> Any:
        """Read an endpoint and return its JSON content.

        ``authenticated`` tells the endpoint needs a password. Without password
        such an endpoint is never requested.
        """
        if authenticated and self._password is None:
            raise BboxAuthError(f"The endpoint {endpoint} requires a password")

        if self._password is not None and not self._logged_in:
            await self._async_login(self._login_generation)

        generation = self._login_generation
        try:
            return await self._async_get(endpoint)
        except BboxAuthError:
            if self._password is None:
                raise

        # Expired session: log in again and try once more, no more.
        _LOGGER.debug("Session refused by the Bbox for %s, logging in again", endpoint)
        await self._async_login(generation)
        return await self._async_get(endpoint)

    async def _async_get(self, endpoint: str) -> Any:
        params = {"btoken": self._token} if self._token else None
        response = await self._request("GET", endpoint, params=params)
        self._raise_for_status(endpoint, response)
        try:
            payload = json.loads(response.text)
        except ValueError as err:
            raise BboxResponseError(f"Invalid JSON returned by {endpoint}") from err
        if not isinstance(payload, dict | list):
            raise BboxResponseError(f"Unexpected content returned by {endpoint}")
        return payload

    async def _async_login(self, generation: int, *, force: bool = False) -> None:
        """Log in. Skipped when another request already did it meanwhile."""
        async with self._login_lock:
            if generation != self._login_generation and not force:
                return
            self._logged_in = False
            self._cookies = {}
            self._token = None

            response = await self._request(
                "POST",
                LOGIN_ENDPOINT,
                data={"password": self._password, "remember": "1"},
            )
            if response.status in (401, 403):
                raise BboxLoginError("Login refused by the Bbox")
            self._raise_for_status(LOGIN_ENDPOINT, response)

            self._cookies = dict(response.cookies)
            self._logged_in = True
            self._login_generation += 1
            await self._async_fetch_token()

    async def _async_fetch_token(self) -> None:
        """Read the session token. The session cookie is kept when it fails."""
        try:
            payload = await self._async_get(TOKEN_ENDPOINT)
        except BboxError as err:
            _LOGGER.debug("No session token available (%s)", err)
            return
        if isinstance(payload, list) and payload:
            payload = payload[0]
        token = (
            payload.get("device", {}).get("token")
            if isinstance(payload, dict)
            else None
        )
        if isinstance(token, str) and token:
            self._token = token

    @staticmethod
    def _raise_for_status(endpoint: str, response: _Response) -> None:
        status = response.status
        if 300 <= status < 400:
            raise BboxRedirectError(
                f"{endpoint} redirected to {response.location or 'another address'}",
                response.location,
            )
        if status in (401, 403):
            raise BboxAuthError(f"{endpoint} requires authentication")
        if status == 404:
            raise BboxNotFoundError(f"{endpoint} does not exist on this Bbox")
        if status >= 400 or status < 200:
            raise BboxResponseError(f"{endpoint} answered HTTP {status}")

    async def _request(
        self,
        method: str,
        endpoint: str,
        *,
        params: dict[str, str] | None = None,
        data: dict[str, str | None] | None = None,
    ) -> _Response:
        """Send one request. Only GET, and the POST of the login, are allowed."""
        if method != "GET" and not (method == "POST" and endpoint == LOGIN_ENDPOINT):
            raise ValueError(f"{method} {endpoint} is not allowed: read-only client")

        headers = {"Accept": "application/json"}
        if self._cookies:
            headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in self._cookies.items())

        try:
            async with self._session.request(
                method,
                f"{self._base_url}{endpoint}",
                params=params,
                data=data,
                headers=headers,
                allow_redirects=False,
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
            ) as response:
                text = await response.text()
                location = response.headers.get("Location")
                cookies = {
                    name: cookie.value for name, cookie in response.cookies.items()
                }
                return _Response(response.status, text, location, cookies)
        except aiohttp.ClientConnectorDNSError as err:
            raise BboxDnsError(f"Unable to resolve {self._host}") from err
        except aiohttp.ClientConnectorError as err:
            if isinstance(err.os_error, socket.gaierror):
                raise BboxDnsError(f"Unable to resolve {self._host}") from err
            raise BboxConnectionError(f"Unable to connect to {self._host}") from err
        except TimeoutError as err:
            raise BboxConnectionError(f"Timeout while requesting {endpoint}") from err
        except aiohttp.ClientError as err:
            raise BboxConnectionError(
                f"Error while requesting {endpoint}: {err}"
            ) from err
