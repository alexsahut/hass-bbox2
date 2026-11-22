"""Test the Bbox config flow."""

from unittest.mock import MagicMock, patch

import aiohttp
import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import TextSelector, TextSelectorType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.bbox.const import DOMAIN

from .conftest import FakeBox
from .const import BOX_ID, LAN_MAC, MOCK_PUBLIC_INPUT, MOCK_USER_INPUT


@pytest.fixture(autouse=True)
def mock_setup_entry():
    """Override async_setup_entry."""
    with patch("custom_components.bbox.async_setup_entry", return_value=True):
        yield


async def start(hass: HomeAssistant, user_input: dict):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"
    assert not result.get("errors")
    return await hass.config_entries.flow.async_configure(result["flow_id"], user_input)


async def test_form_success_with_password(hass: HomeAssistant, router: FakeBox) -> None:
    """With a password: login, the LAN MAC address identifies the box."""
    result = await start(hass, MOCK_USER_INPUT)

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "Bouygues Bbox"
    assert result["data"] == MOCK_USER_INPUT
    assert result["result"].unique_id == BOX_ID
    assert router.count("login", "POST") == 1
    assert router.count("device/summary") == 0


async def test_form_success_without_password(
    hass: HomeAssistant, public_router: FakeBox
) -> None:
    """Without password: no login, only public endpoints, the LAN MAC identifies it."""
    result = await start(
        hass, {k: v for k, v in MOCK_PUBLIC_INPUT.items() if k != "password"}
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"]["password"] == ""
    assert result["result"].unique_id == BOX_ID
    assert public_router.requests == [("GET", "lan/ip")]


async def test_form_normalizes_the_mac_address(
    hass: HomeAssistant, public_router: FakeBox
) -> None:
    """The identifier is the normalized MAC address, whatever its case."""
    public_router.route("lan/ip", [{"lan": {"ip": {"mac": LAN_MAC.upper()}}}])
    result = await start(hass, MOCK_PUBLIC_INPUT)
    assert result["result"].unique_id == BOX_ID


@pytest.mark.parametrize(
    ("route", "error"),
    [
        # The IP of the box: 302 to mabbox.bytel.fr
        (
            {
                "status": 302,
                "headers": {"Location": "https://mabbox.bytel.fr:443/api/v1/lan/ip"},
            },
            "redirect",
        ),
        # The host name does not resolve
        (
            {"exc": aiohttp.ClientConnectorDNSError(MagicMock(), OSError("dns"))},
            "dns_error",
        ),
        # The box does not answer
        (
            {
                "exc": aiohttp.ClientConnectorError(
                    MagicMock(), ConnectionRefusedError()
                )
            },
            "cannot_connect",
        ),
        ({"exc": TimeoutError()}, "cannot_connect"),
        # Not a Bbox
        ({"status": 404}, "invalid_response"),
        ({"text": "<html>"}, "invalid_response"),
        # No identifier in the answer
        ({"payload": [{"lan": {"ip": {}}}]}, "no_identifier"),
    ],
)
async def test_form_errors_without_password(
    hass: HomeAssistant, public_router: FakeBox, route, error
) -> None:
    """Connection problems are explicit and distinct, the form is shown again."""
    public_router.route("lan/ip", **route)

    result = await start(hass, MOCK_PUBLIC_INPUT)

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": error}


async def test_form_ip_redirect_with_password(
    hass: HomeAssistant, router: FakeBox
) -> None:
    """The login on the IP of the box is redirected: explicit error, no retry."""
    router.route(
        "login",
        status=302,
        headers={"Location": "https://mabbox.bytel.fr:443/api/v1/login"},
        method="POST",
    )
    result = await start(hass, {**MOCK_USER_INPUT, "host": "192.168.1.254"})

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "redirect"}
    assert router.count("login", "POST") == 1


async def test_form_dns_error_with_password(
    hass: HomeAssistant, router: FakeBox
) -> None:
    router.route(
        "login",
        exc=aiohttp.ClientConnectorDNSError(MagicMock(), OSError("dns")),
        method="POST",
    )
    result = await start(hass, MOCK_USER_INPUT)
    assert result["errors"] == {"base": "dns_error"}


async def test_form_invalid_auth(hass: HomeAssistant, router: FakeBox) -> None:
    """A refused login (wrong password)."""
    router.route("login", status=401, method="POST")
    result = await start(hass, MOCK_USER_INPUT)

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_form_cannot_connect(hass: HomeAssistant, router: FakeBox) -> None:
    """The box does not answer."""
    router.route(
        "login",
        exc=aiohttp.ClientConnectorError(MagicMock(), OSError("refused")),
        method="POST",
    )
    result = await start(hass, MOCK_USER_INPUT)
    assert result["errors"] == {"base": "cannot_connect"}


async def test_form_without_identifier(hass: HomeAssistant, router: FakeBox) -> None:
    """No LAN MAC address: explicit error."""
    router.route("lan/ip", [{"lan": {"ip": {}}}])
    result = await start(hass, MOCK_USER_INPUT)
    assert result["errors"] == {"base": "no_identifier"}


async def test_form_error_then_success(hass: HomeAssistant, router: FakeBox) -> None:
    """After an error the user can correct and submit again."""
    router.route("login", status=401, method="POST", then=[{"status": 200, "json": {}}])
    result = await start(hass, MOCK_USER_INPUT)
    assert result["errors"] == {"base": "invalid_auth"}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], MOCK_USER_INPUT
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY


async def test_form_already_configured(hass: HomeAssistant, router: FakeBox) -> None:
    """The flow aborts if the box (LAN MAC address) is already configured."""
    MockConfigEntry(domain=DOMAIN, unique_id=BOX_ID, data=MOCK_USER_INPUT).add_to_hass(
        hass
    )
    result = await start(hass, MOCK_USER_INPUT)
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_form_already_configured_without_password(
    hass: HomeAssistant, router: FakeBox
) -> None:
    """A box configured without password is detected when adding it with one."""
    MockConfigEntry(
        domain=DOMAIN, unique_id=BOX_ID, data=MOCK_PUBLIC_INPUT
    ).add_to_hass(hass)
    result = await start(hass, MOCK_USER_INPUT)
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_form_ip_host_disables_ssl_verification(
    hass: HomeAssistant, public_router: FakeBox
) -> None:
    """SSL verification is disabled when the host is an IP address."""
    with patch(
        "custom_components.bbox.config_flow.async_get_clientsession",
        wraps=async_get_clientsession,
    ) as get_session:
        public_router.routes.clear()
        public_router.route("lan/ip", [{"lan": {"ip": {"mac": LAN_MAC}}}])
        result = await start(hass, {**MOCK_PUBLIC_INPUT, "host": " 192.168.1.254 "})

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"]["verify_ssl"] is False
    assert result["data"]["host"] == "192.168.1.254"
    assert get_session.call_args.kwargs == {"verify_ssl": False}


async def test_form_verify_ssl_kept_for_a_host_name(
    hass: HomeAssistant, public_router: FakeBox
) -> None:
    with patch(
        "custom_components.bbox.config_flow.async_get_clientsession",
        wraps=async_get_clientsession,
    ) as get_session:
        result = await start(hass, MOCK_PUBLIC_INPUT)
    assert result["data"]["verify_ssl"] is True
    assert get_session.call_args.kwargs == {"verify_ssl": True}


def assert_password_is_masked(result) -> None:
    """The password field uses a password selector, never a clear text field."""
    schema = result["data_schema"].schema
    selector = next(v for k, v in schema.items() if k == "password")
    assert isinstance(selector, TextSelector)
    assert selector.config["type"] == TextSelectorType.PASSWORD


async def test_form_password_is_masked(hass: HomeAssistant) -> None:
    """The user step masks the password input."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert_password_is_masked(result)


# --- re-authentication -------------------------------------------------------


async def start_reauth(hass: HomeAssistant, entry: MockConfigEntry):
    entry.add_to_hass(hass)
    result = await entry.start_reauth_flow(hass)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"
    assert_password_is_masked(result)
    return result


async def test_reauth_new_password(hass: HomeAssistant, router: FakeBox) -> None:
    entry = MockConfigEntry(domain=DOMAIN, unique_id=BOX_ID, data=MOCK_USER_INPUT)
    result = await start_reauth(hass, entry)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"password": "new_password"}
    )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data["password"] == "new_password"
    assert entry.unique_id == BOX_ID


async def test_reauth_wrong_password(hass: HomeAssistant, router: FakeBox) -> None:
    entry = MockConfigEntry(domain=DOMAIN, unique_id=BOX_ID, data=MOCK_USER_INPUT)
    result = await start_reauth(hass, entry)
    router.route("login", status=401, method="POST")

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"password": "wrong"}
    )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}
    assert entry.data["password"] == MOCK_USER_INPUT["password"]


async def test_reauth_without_password(hass: HomeAssistant, router: FakeBox) -> None:
    """The password is optional: empty switches to the public data only."""
    entry = MockConfigEntry(domain=DOMAIN, unique_id=BOX_ID, data=MOCK_USER_INPUT)
    result = await start_reauth(hass, entry)
    router.requests.clear()

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data["password"] == ""
    # the identifier does not depend on the password
    assert entry.unique_id == BOX_ID
    assert router.requests == [("GET", "lan/ip")]


async def test_reauth_adds_a_password(hass: HomeAssistant, router: FakeBox) -> None:
    """An entry without password can get one: the identifier is unchanged."""
    entry = MockConfigEntry(domain=DOMAIN, unique_id=BOX_ID, data=MOCK_PUBLIC_INPUT)
    result = await start_reauth(hass, entry)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"password": "mock_password"}
    )

    assert result["reason"] == "reauth_successful"
    assert entry.data["password"] == "mock_password"
    assert entry.unique_id == BOX_ID


@pytest.mark.parametrize("password", ["mock_password", ""])
async def test_reauth_wrong_box(
    hass: HomeAssistant, router: FakeBox, password: str
) -> None:
    """Another box is detected, with or without password."""
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="02:00:00:00:00:ff", data=MOCK_USER_INPUT
    )
    result = await start_reauth(hass, entry)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"password": password}
    )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "wrong_account"
    assert entry.data["password"] == MOCK_USER_INPUT["password"]


async def test_reauth_without_identifier(hass: HomeAssistant, router: FakeBox) -> None:
    entry = MockConfigEntry(domain=DOMAIN, unique_id=BOX_ID, data=MOCK_USER_INPUT)
    result = await start_reauth(hass, entry)
    router.route("lan/ip", [{}])

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"password": "mock_password"}
    )
    assert result["errors"] == {"base": "no_identifier"}


async def test_reauth_redirect(hass: HomeAssistant, router: FakeBox) -> None:
    """Reauth on an entry configured with an IP gets the explicit redirect error."""
    entry = MockConfigEntry(domain=DOMAIN, unique_id=BOX_ID, data=MOCK_USER_INPUT)
    result = await start_reauth(hass, entry)
    router.route("login", status=302, method="POST")

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"password": "mock_password"}
    )
    assert result["errors"] == {"base": "redirect"}


async def test_options_flow(hass: HomeAssistant, router: FakeBox) -> None:
    """The options (refresh rate, device tracking) are unchanged."""
    entry = MockConfigEntry(domain=DOMAIN, unique_id=BOX_ID, data=MOCK_USER_INPUT)
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == FlowResultType.FORM
    defaults = {str(key): key.default() for key in result["data_schema"].schema}
    # device tracking is off by default (one device per host of the box)
    assert defaults == {"refresh_rate": 60, "track_devices": False}
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"refresh_rate": 120, "track_devices": False}
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.options == {"refresh_rate": 120, "track_devices": False}


# --- reconfiguration ---------------------------------------------------------


async def start_reconfigure(hass: HomeAssistant, entry: MockConfigEntry):
    entry.add_to_hass(hass)
    result = await entry.start_reconfigure_flow(hass)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "reconfigure"
    assert_password_is_masked(result)
    return result


def reconfigure_input(**changes) -> dict:
    data = {k: v for k, v in MOCK_USER_INPUT.items() if k != "password"}
    return {**data, **changes}


async def test_reconfigure_form_never_shows_the_password(
    hass: HomeAssistant, router: FakeBox
) -> None:
    """The current password is not sent back to the form."""
    entry = MockConfigEntry(domain=DOMAIN, unique_id=BOX_ID, data=MOCK_USER_INPUT)
    result = await start_reconfigure(hass, entry)

    for key in result["data_schema"].schema:
        suggested = (key.description or {}).get("suggested_value")
        assert suggested != MOCK_USER_INPUT["password"], key
        if key == "host":
            assert suggested == "mabbox.bytel.fr"
    assert "remove_password" in result["data_schema"].schema


async def test_reconfigure_adds_a_password(
    hass: HomeAssistant, router: FakeBox
) -> None:
    """An entry without password gets one: login, same identifier."""
    entry = MockConfigEntry(domain=DOMAIN, unique_id=BOX_ID, data=MOCK_PUBLIC_INPUT)
    result = await start_reconfigure(hass, entry)
    # without password, there is nothing to remove
    assert "remove_password" not in result["data_schema"].schema

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], reconfigure_input(password="mock_password")
    )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data == MOCK_USER_INPUT
    assert entry.unique_id == BOX_ID
    assert router.count("login", "POST") == 1


async def test_reconfigure_keeps_the_password(
    hass: HomeAssistant, router: FakeBox
) -> None:
    """An empty password field keeps the current password; the host changes."""
    entry = MockConfigEntry(domain=DOMAIN, unique_id=BOX_ID, data=MOCK_USER_INPUT)
    result = await start_reconfigure(hass, entry)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], reconfigure_input(host=" bbox.lan ", verify_ssl=False)
    )

    assert result["reason"] == "reconfigure_successful"
    assert entry.data == {
        **MOCK_USER_INPUT,
        "host": "bbox.lan",
        "verify_ssl": False,
    }
    assert router.count("login", "POST") == 1


async def test_reconfigure_changes_the_password(
    hass: HomeAssistant, router: FakeBox
) -> None:
    entry = MockConfigEntry(domain=DOMAIN, unique_id=BOX_ID, data=MOCK_USER_INPUT)
    result = await start_reconfigure(hass, entry)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], reconfigure_input(password="new_password")
    )

    assert result["reason"] == "reconfigure_successful"
    assert entry.data["password"] == "new_password"


async def test_reconfigure_removes_the_password(
    hass: HomeAssistant, router: FakeBox
) -> None:
    """Remove: no login, public endpoints only, same identifier."""
    entry = MockConfigEntry(domain=DOMAIN, unique_id=BOX_ID, data=MOCK_USER_INPUT)
    result = await start_reconfigure(hass, entry)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], reconfigure_input(remove_password=True)
    )

    assert result["reason"] == "reconfigure_successful"
    assert entry.data == MOCK_PUBLIC_INPUT
    assert entry.unique_id == BOX_ID
    assert router.requests == [("GET", "lan/ip")]


async def test_reconfigure_password_and_remove(
    hass: HomeAssistant, router: FakeBox
) -> None:
    """A new password and the removal together: explicit error, nothing read."""
    entry = MockConfigEntry(domain=DOMAIN, unique_id=BOX_ID, data=MOCK_USER_INPUT)
    result = await start_reconfigure(hass, entry)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        reconfigure_input(password="new_password", remove_password=True),
    )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "password_and_remove"}
    assert router.requests == []
    assert entry.data == MOCK_USER_INPUT


async def test_reconfigure_ip_host_disables_ssl_verification(
    hass: HomeAssistant, public_router: FakeBox
) -> None:
    entry = MockConfigEntry(domain=DOMAIN, unique_id=BOX_ID, data=MOCK_PUBLIC_INPUT)
    result = await start_reconfigure(hass, entry)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], reconfigure_input(host="192.168.1.254")
    )

    assert result["reason"] == "reconfigure_successful"
    assert entry.data["host"] == "192.168.1.254"
    assert entry.data["verify_ssl"] is False


@pytest.mark.parametrize("password", ["mock_password", ""])
async def test_reconfigure_wrong_box(
    hass: HomeAssistant, router: FakeBox, password: str
) -> None:
    """Another box (other LAN MAC address): abort, the entry is unchanged."""
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="02:00:00:00:00:ff", data=MOCK_PUBLIC_INPUT
    )
    result = await start_reconfigure(hass, entry)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], reconfigure_input(password=password)
    )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "wrong_account"
    assert entry.data == MOCK_PUBLIC_INPUT
    assert entry.unique_id == "02:00:00:00:00:ff"


async def test_reconfigure_error_then_success(
    hass: HomeAssistant, router: FakeBox
) -> None:
    """A refused password: error, the form keeps the host but not the password."""
    entry = MockConfigEntry(domain=DOMAIN, unique_id=BOX_ID, data=MOCK_PUBLIC_INPUT)
    result = await start_reconfigure(hass, entry)
    router.route("login", status=401, method="POST", then=[{"status": 200, "json": {}}])

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], reconfigure_input(host="bbox.lan", password="wrong")
    )
    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}
    suggested = {
        k: (k.description or {}).get("suggested_value")
        for k in result["data_schema"].schema
    }
    assert suggested["host"] == "bbox.lan"
    assert suggested["password"] is None
    assert entry.data == MOCK_PUBLIC_INPUT

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], reconfigure_input(password="mock_password")
    )
    assert result["reason"] == "reconfigure_successful"
    assert entry.data == MOCK_USER_INPUT


async def test_reconfigure_without_identifier(
    hass: HomeAssistant, router: FakeBox
) -> None:
    entry = MockConfigEntry(domain=DOMAIN, unique_id=BOX_ID, data=MOCK_USER_INPUT)
    result = await start_reconfigure(hass, entry)
    router.route("lan/ip", [{}])

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], reconfigure_input()
    )
    assert result["errors"] == {"base": "no_identifier"}
