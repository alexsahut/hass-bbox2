"""Test data: real answers of a F@st 5696b (public endpoints) and older captures."""

import json
from pathlib import Path

from pytest_homeassistant_custom_component.common import load_json_object_fixture

FIXTURES = Path(__file__).parent / "fixtures"
F5696B = FIXTURES / "f5696b"


def load_f5696b(name: str):
    """Return a real (anonymized) answer of the 5696b, named like its file."""
    return json.loads((F5696B / f"{name}.json").read_text())


# Public endpoints: real answers (list of one element, as the Bbox sends them).
PUBLIC_ANSWERS = {
    "device": load_f5696b("device"),
    "device/cpu": load_f5696b("device_cpu"),
    "device/mem": load_f5696b("device_mem"),
    "device/led": load_f5696b("device_led"),
    "wan/ip": load_f5696b("wan_ip"),
    "wan/ip/stats": load_f5696b("wan_ip_stats"),
    "summary": load_f5696b("summary"),
    "wireless/wps": load_f5696b("wireless_wps"),
    "lan/ip": load_f5696b("lan_ip"),
}

SERIAL = "012345678901234"
LAN_MAC = PUBLIC_ANSWERS["lan/ip"][0]["lan"]["ip"]["mac"]

# Endpoints which need a password: no real capture exists, the older fixtures
# (upstream data) are used. With a password, `device` also gives the serial.
INFO = [load_json_object_fixture("info.json")]
DEVICES = [load_json_object_fixture("devices.json")]
WIFI = [load_json_object_fixture("wifi.json")]
SPEEDTEST_INFOS = [load_json_object_fixture("speedtest.json")]

AUTHENTICATED_ANSWERS = {
    "hosts": DEVICES,
    "wireless": WIFI,
    "speedtest/info": SPEEDTEST_INFOS,
    "device/summary": INFO,
}

DEVICE_WITH_SERIAL = json.loads(json.dumps(PUBLIC_ANSWERS["device"]))
DEVICE_WITH_SERIAL[0]["device"]["serialnumber"] = SERIAL

MOCK_USER_INPUT = {
    "host": "mabbox.bytel.fr",
    "password": "mock_password",
    "use_tls": True,
    "verify_ssl": True,
}
MOCK_PUBLIC_INPUT = {**MOCK_USER_INPUT, "password": ""}
