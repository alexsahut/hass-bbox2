"""Tests of the read-only API client (HTTP is mocked, no network)."""

import asyncio
import socket
from unittest.mock import MagicMock

import aiohttp
import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from custom_components.bbox.api import (
    BboxAuthError,
    BboxClient,
    BboxConnectionError,
    BboxDnsError,
    BboxLoginError,
    BboxNotFoundError,
    BboxRedirectError,
    BboxResponseError,
)

from .conftest import FakeBox

PASSWORD = "mock_password"


@pytest.fixture(name="session")
def get_session(hass: HomeAssistant) -> aiohttp.ClientSession:
    """Return the (mocked) session provided by Home Assistant."""
    return async_get_clientsession(hass)


def client_for(session, *, password=None, **kwargs) -> BboxClient:
    return BboxClient(session, "mabbox.bytel.fr", password=password, **kwargs)


async def test_public_get(session, public_router: FakeBox, aioclient_mock) -> None:
    """A public endpoint is read with a plain GET on the canonical host."""
    data = await client_for(session).async_get("device")

    assert data[0]["device"]["modelname"] == "F@st5696b"
    assert len(aioclient_mock.mock_calls) == 1
    method, url, _data, headers = aioclient_mock.mock_calls[0]
    assert method == "GET"
    assert str(url) == "https://mabbox.bytel.fr/api/v1/device"
    assert "Cookie" not in headers


async def test_request_options() -> None:
    """Redirects are not followed, TLS is left to the session, no verify_ssl kwarg."""
    response = MagicMock(status=200, headers={}, cookies={})

    async def text() -> str:
        return "[]"

    response.text = text
    context = MagicMock()
    context.__aenter__ = MagicMock(side_effect=lambda: _return(response))
    context.__aexit__ = MagicMock(side_effect=lambda *a: _return(None))
    session = MagicMock()
    session.request.return_value = context

    await client_for(session).async_get("device")

    args, kwargs = session.request.call_args
    assert args == ("GET", "https://mabbox.bytel.fr/api/v1/device")
    assert kwargs["allow_redirects"] is False
    assert "verify_ssl" not in kwargs
    assert "ssl" not in kwargs


async def _return(value):
    return value


@pytest.mark.parametrize(
    ("kwargs", "host", "expected"),
    [
        ({}, "mabbox.bytel.fr", "https://mabbox.bytel.fr/api/v1/"),
        ({"use_tls": False}, "mabbox.bytel.fr", "http://mabbox.bytel.fr/api/v1/"),
        ({}, "2001:db8::1", "https://[2001:db8::1]/api/v1/"),
        ({}, "192.0.2.1", "https://192.0.2.1/api/v1/"),
    ],
)
async def test_base_url(session, public_router, aioclient_mock, kwargs, host, expected):
    """The base URL is built from the scheme and the host."""
    public_router.mock.request("GET", expected + "device", json=[{}])
    await BboxClient(session, host, **kwargs).async_get("device")
    assert str(aioclient_mock.mock_calls[0][1]) == expected + "device"


async def test_redirect_error(session, public_router: FakeBox) -> None:
    """A 302 (IP address of the box) is a typed error, not followed."""
    public_router.route(
        "device",
        status=302,
        headers={"Location": "https://mabbox.bytel.fr:443/api/v1/device"},
    )
    with pytest.raises(BboxRedirectError) as err:
        await client_for(session).async_get("device")
    assert err.value.location == "https://mabbox.bytel.fr:443/api/v1/device"
    assert "mabbox.bytel.fr" in str(err.value)


async def test_not_found(session, public_router: FakeBox) -> None:
    public_router.route("wan/xdsl", status=404)
    with pytest.raises(BboxNotFoundError):
        await client_for(session).async_get("wan/xdsl")


@pytest.mark.parametrize(
    ("kwargs"),
    [
        {"status": 500},
        {"text": "not json"},
        {"text": ""},
        {"text": "42"},
    ],
)
async def test_invalid_response(session, public_router: FakeBox, kwargs) -> None:
    public_router.route("device", **kwargs)
    with pytest.raises(BboxResponseError):
        await client_for(session).async_get("device")


def _connector_error(os_error: OSError, dns: bool = False) -> Exception:
    key = MagicMock()
    if dns:
        return aiohttp.ClientConnectorDNSError(key, os_error)
    return aiohttp.ClientConnectorError(key, os_error)


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (_connector_error(OSError(), dns=True), BboxDnsError),
        (_connector_error(socket.gaierror(-2, "Name not known")), BboxDnsError),
        (_connector_error(ConnectionRefusedError()), BboxConnectionError),
        (TimeoutError(), BboxConnectionError),
        (aiohttp.ClientError("boom"), BboxConnectionError),
    ],
)
async def test_connection_errors(session, public_router, exc, expected) -> None:
    public_router.route("device", exc=exc)
    with pytest.raises(expected) as err:
        await client_for(session).async_get("device")
    assert type(err.value) is expected or expected is BboxConnectionError


async def test_dns_error_is_distinct() -> None:
    """The DNS error is a connection error, but a more specific one."""
    assert issubclass(BboxDnsError, BboxConnectionError)
    assert not issubclass(BboxRedirectError, BboxConnectionError)
    assert issubclass(BboxLoginError, BboxAuthError)


async def test_login_and_session(session, router: FakeBox, aioclient_mock) -> None:
    """Login once, then send the cookie and the token with each request."""
    client = client_for(session, password=PASSWORD)
    await client.async_get("device/mem")
    await client.async_get("device/cpu")

    assert router.count("login", "POST") == 1
    calls = aioclient_mock.mock_calls
    login = calls[0]
    assert login[0] == "POST"
    assert login[2]["password"] == PASSWORD
    assert str(calls[0][1]) == "https://mabbox.bytel.fr/api/v1/login"
    # every request after the login carries the session
    for _method, url, _data, headers in calls[1:]:
        assert headers["Cookie"] == "BBOX_ID=session-1"
        if str(url).endswith(("device/mem", "device/cpu")):
            assert url.query["btoken"] == "token-1"


@pytest.mark.parametrize(
    "token_answer",
    [
        {"status": 404},
        {"status": 200, "text": "garbage"},
        {"status": 200, "payload": {"device": {}}},
        {"status": 200, "payload": [{"device": {"token": "t2"}}]},
        {"status": 200, "payload": {"device": {"token": "t3"}}},
    ],
)
async def test_token_is_optional(session, router: FakeBox, token_answer) -> None:
    """A missing or odd token does not prevent reading with the session cookie."""
    router.route("device/token", **token_answer)
    client = client_for(session, password=PASSWORD)
    assert await client.async_get("device/mem")


async def test_no_password_never_logs_in(session, public_router: FakeBox) -> None:
    """Without password: no login, and an authenticated endpoint is not requested."""
    client = client_for(session)
    assert client.has_password is False
    await client.async_get("device")

    with pytest.raises(BboxAuthError):
        await client.async_get("hosts", authenticated=True)
    with pytest.raises(BboxLoginError):
        await client.async_login()

    assert public_router.requests == [("GET", "device")]


async def test_public_401_without_password(session, public_router: FakeBox) -> None:
    """Without password a 401 is an error: there is nothing to log in with."""
    public_router.route("device", status=401)
    with pytest.raises(BboxAuthError):
        await client_for(session).async_get("device")
    assert public_router.count("device") == 1
    assert public_router.count("login", "POST") == 0


async def test_401_then_relogin_then_success(session, router: FakeBox) -> None:
    """A 401 triggers a new login and ONE new attempt, which succeeds."""
    client = client_for(session, password=PASSWORD)
    await client.async_get("device/mem")  # first session
    router.route("hosts", status=401, then=[{"status": 200, "json": [{"hosts": {}}]}])
    router.route("login", {}, method="POST", cookies={"BBOX_ID": "session-2"})

    assert await client.async_get("hosts", authenticated=True) == [{"hosts": {}}]

    assert router.count("hosts") == 2
    assert router.count("login", "POST") == 2


async def test_401_then_login_refused(session, router: FakeBox) -> None:
    """A 401 then a refused login (wrong password) is a login error."""
    client = client_for(session, password=PASSWORD)
    await client.async_get("device/mem")
    router.route("hosts", status=401)
    router.route("login", status=401, method="POST")

    with pytest.raises(BboxLoginError):
        await client.async_get("hosts", authenticated=True)

    assert router.count("hosts") == 1
    assert router.count("login", "POST") == 2


async def test_401_after_relogin_is_not_retried_again(session, router: FakeBox) -> None:
    """A single new attempt: a second 401 is an error, not a loop."""
    client = client_for(session, password=PASSWORD)
    router.route("hosts", status=401)

    with pytest.raises(BboxAuthError) as err:
        await client.async_get("hosts", authenticated=True)

    assert not isinstance(err.value, BboxLoginError)
    assert router.count("hosts") == 2
    assert router.count("login", "POST") == 2  # initial login + one new login


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        ({"status": 401}, BboxLoginError),
        ({"status": 403}, BboxLoginError),
        ({"status": 302}, BboxRedirectError),
        ({"status": 500}, BboxResponseError),
        ({"exc": aiohttp.ClientError()}, BboxConnectionError),
    ],
)
async def test_login_errors(session, router: FakeBox, answer, expected) -> None:
    router.route("login", method="POST", **answer)
    with pytest.raises(expected):
        await client_for(session, password=PASSWORD).async_get("device")
    assert router.count("device") == 0


async def test_concurrent_requests_log_in_once(session, router: FakeBox) -> None:
    """Concurrent requests share one login."""
    client = client_for(session, password=PASSWORD)
    await asyncio.gather(
        *(client.async_get(e) for e in ("device", "device/mem", "device/cpu"))
    )
    assert router.count("login", "POST") == 1


async def test_concurrent_401_log_in_once(session, router: FakeBox) -> None:
    """Concurrent 401s (expired session) share one new login."""
    client = client_for(session, password=PASSWORD)
    await client.async_get("device")
    for endpoint in ("device/mem", "device/cpu", "device/led"):
        router.route(
            endpoint, status=401, then=[{"status": 200, "json": [{"ok": endpoint}]}]
        )
    await asyncio.gather(
        *(client.async_get(e) for e in ("device/mem", "device/cpu", "device/led"))
    )
    assert router.count("login", "POST") == 2


async def test_explicit_login(session, router: FakeBox) -> None:
    """The public login logs in even if a session exists (used by the config flow)."""
    client = client_for(session, password=PASSWORD)
    await client.async_login()
    await client.async_login()
    assert router.count("login", "POST") == 2
    assert client.host == "mabbox.bytel.fr"


async def test_client_is_read_only(session, router: FakeBox) -> None:
    """No public method writes; only GET and the POST of the login can be sent."""
    public = {name for name in dir(BboxClient) if not name.startswith("_")}
    assert public == {"async_login", "async_get", "host", "has_password"}

    client = client_for(session, password=PASSWORD)
    for method, endpoint in (
        ("PUT", "wireless"),
        ("DELETE", "voip/calllog/1"),
        ("PATCH", "device"),
        ("POST", "device/reboot"),
        ("POST", "device/factory"),
        ("POST", "wireless/wps"),
        ("HEAD", "device"),
    ):
        with pytest.raises(ValueError, match="read-only"):
            await client._request(method, endpoint)

    assert router.requests == []
