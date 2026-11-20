"""The tests for the bbox component."""

import asyncio
import re
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from homeassistant.config_entries import SOURCE_USER, ConfigEntry
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
    AiohttpClientMockResponse,
)
from yarl import URL

from custom_components.bbox.const import DOMAIN

from .const import (
    AUTHENTICATED_ANSWERS,
    BOX_ID,
    DEVICE_WITH_SERIAL,
    MOCK_PUBLIC_INPUT,
    MOCK_USER_INPUT,
    PUBLIC_ANSWERS,
)

API = "https://mabbox.bytel.fr/api/v1/"


class FakeBox:
    """A Bbox simulated at the HTTP level (no network, aiohttp is mocked).

    A route is a list of answers, consumed in order; the last one is repeated.
    A request without route fails the test: it is how the tests prove that an
    endpoint is not called.
    """

    def __init__(self, mock: AiohttpClientMocker) -> None:
        """Register the catch-all routes in the aiohttp mock."""
        self.mock = mock
        self.routes: dict[tuple[str, str], list[dict[str, Any]]] = {}
        self.requests: list[tuple[str, str]] = []
        pattern = re.compile(r"^https?://[^/]+/api/v1/")
        for method in ("GET", "POST"):
            mock.request(method, pattern, side_effect=self._handle)

    def route(
        self,
        endpoint: str,
        payload: Any = None,
        *,
        status: int = 200,
        exc: Exception | None = None,
        text: str | None = None,
        headers: dict[str, str] | None = None,
        cookies: dict[str, str] | None = None,
        method: str = "GET",
        then: list[dict[str, Any]] | None = None,
    ) -> None:
        """Define the answer(s) of an endpoint."""
        first = {
            "status": status,
            "exc": exc,
            "text": text if text is not None else None,
            "json": payload,
            "headers": headers,
            "cookies": cookies,
        }
        self.routes[(method, endpoint)] = [first, *(then or [])]

    async def _handle(self, method: str, url: URL, data: Any) -> Any:
        await asyncio.sleep(0)  # a real request yields to the event loop
        endpoint = url.path.removeprefix("/api/v1/")
        self.requests.append((method, endpoint))
        answers = self.routes.get((method, endpoint))
        if answers is None:
            raise AssertionError(f"Unexpected request {method} {endpoint}")
        answer = answers.pop(0) if len(answers) > 1 else answers[0]
        return AiohttpClientMockResponse(method, url, **answer)

    def count(self, endpoint: str, method: str = "GET") -> int:
        """Return how many times an endpoint has been requested."""
        return self.requests.count((method, endpoint))

    @property
    def endpoints(self) -> set[str]:
        """Return the endpoints requested with GET."""
        return {e for m, e in self.requests if m == "GET"}


def _public(box: FakeBox) -> None:
    for endpoint, payload in PUBLIC_ANSWERS.items():
        box.route(endpoint, payload)


def _full(box: FakeBox) -> None:
    _public(box)
    box.route("device", DEVICE_WITH_SERIAL)
    for endpoint, payload in AUTHENTICATED_ANSWERS.items():
        box.route(endpoint, payload)
    box.route("login", {}, method="POST", cookies={"BBOX_ID": "session-1"})
    box.route("device/token", [{"device": {"token": "token-1"}}])


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations for hass."""
    yield


@pytest.fixture(autouse=True)
def read_only_guard(aioclient_mock: AiohttpClientMocker) -> Iterator[None]:
    """Every HTTP request of every test is a GET, except the POST of the login."""
    yield
    for method, url, _data, _headers in aioclient_mock.mock_calls:
        assert method.upper() in ("GET", "POST"), f"{method} {url}"
        if method.upper() == "POST":
            assert url.path == "/api/v1/login", f"POST {url}"


@pytest.fixture(name="box_factory")
def mock_box_factory(
    aioclient_mock: AiohttpClientMocker,
) -> Callable[..., FakeBox]:
    """Return a factory of simulated boxes."""

    def factory(*, password: bool = True) -> FakeBox:
        box = FakeBox(aioclient_mock)
        (_full if password else _public)(box)
        return box

    return factory


@pytest.fixture(name="router")
def mock_router(box_factory) -> FakeBox:
    """A Bbox with a password: public and authenticated endpoints answer."""
    return box_factory(password=True)


@pytest.fixture(name="public_router")
def mock_public_router(box_factory) -> FakeBox:
    """A Bbox without password: the authenticated endpoints must not be called."""
    return box_factory(password=False)


@pytest.fixture(name="config_entry")
def get_config_entry(hass: HomeAssistant) -> ConfigEntry:
    """Create and register mock config entry (with a password)."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        source=SOURCE_USER,
        data=MOCK_USER_INPUT,
        unique_id=BOX_ID,
        options={},
        entry_id="123456",
    )
    config_entry.add_to_hass(hass)
    return config_entry


@pytest.fixture(name="public_config_entry")
def get_public_config_entry(hass: HomeAssistant) -> ConfigEntry:
    """Create and register a mock config entry without password."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        source=SOURCE_USER,
        data=MOCK_PUBLIC_INPUT,
        unique_id=BOX_ID,
        options={},
        entry_id="654321",
    )
    config_entry.add_to_hass(hass)
    return config_entry
