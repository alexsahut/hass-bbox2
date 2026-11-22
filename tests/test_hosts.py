"""Tests of the host names and of the device options (pure functions)."""

import pytest

from custom_components.bbox.hosts import (
    clean,
    device_options,
    fix_text,
    host_label,
    host_name,
    host_names,
    hosts_of,
    mac_suffix,
    tracked_macs,
)

from .const import SYNTHETIC_HOSTS

HOSTS = hosts_of({"devices": SYNTHETIC_HOSTS[0]})
NAMES = host_names(HOSTS)


def mac(n: int) -> str:
    return f"02:00:00:00:00:{n:02x}"


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ({"userfriendlyname": "TV", "hostname": "h"}, "TV"),
        ({"userfriendlyname": "  ", "hostname": "h"}, "h"),
        ({"hostname": "h", "informations": {"manufacturer": "A", "model": "B"}}, "h"),
        ({"hostname": "", "informations": {"manufacturer": "A", "model": "B"}}, "A B"),
        ({"informations": {"manufacturer": "A", "model": ""}}, "A"),
        ({"informations": {"manufacturer": " ", "model": " B "}}, "B"),
        ({"informations": {"manufacturer": None, "model": "null"}}, "04"),
        ({"informations": {"type": "Phone"}}, "Phone"),
        ({"informations": {"type": "Device"}, "devicetype": "Tablet"}, "Tablet"),
        ({"informations": {"type": ""}, "devicetype": "Tablet"}, "Tablet"),
        ({"informations": {"type": "Phone"}, "devicetype": "Tablet"}, "Phone"),
        ({"informations": {"type": "device"}, "devicetype": "Device"}, "04"),
        ({"informations": "not a dict", "hostname": None}, "04"),
        ({"hostname": "None"}, "04"),
        ({}, "04"),
    ],
)
def test_host_name(host: dict, expected: str) -> None:
    """The name follows the rules; the MAC is the very last resort."""
    assert host_name({"macaddress": "04", **host}) == expected


def test_synthetic_names() -> None:
    """Every case of the synthetic fixture."""
    assert {
        mac(1): "synth-laptop",
        mac(2): "Acme Phone X (0002)",
        mac(3): "Acme Phone X (0003)",
        mac(4): "Cam-1",
        mac(5): "Printer",
        mac(6): mac(6),
        mac(7): "Living room TV",
        mac(8): "Set-top box",
        mac(9): "Acme",
        mac(10): "Sensor",
        mac(11): "dup-host (000B)",
        mac(12): "Dup-Host (000C)",
        mac(13): mac(13),
    } == NAMES
    assert all(name and "None" not in name for name in NAMES.values())


def test_duplicates_count_all_the_hosts() -> None:
    """A repeated MAC is one host; a name used twice is suffixed everywhere."""
    hosts = [
        {"macaddress": "AA:BB:CC:DD:A1:B2", "hostname": "Phone"},
        {"macaddress": "aa:bb:cc:dd:a1:b2", "hostname": "Phone"},
        {"macaddress": "aa:bb:cc:dd:c3:d4", "hostname": "Phone"},
        {"macaddress": "aa:bb:cc:dd:00:01", "hostname": "Other"},
        {"hostname": "no mac"},
    ]
    assert host_names(hosts) == {
        "aa:bb:cc:dd:a1:b2": "Phone (A1B2)",
        "aa:bb:cc:dd:c3:d4": "Phone (C3D4)",
        "aa:bb:cc:dd:00:01": "Other",
    }
    assert mac_suffix("aa:bb:cc:dd:a1:b2") == "A1B2"


def test_clean_and_hosts_of() -> None:
    assert [clean(v) for v in (None, " ", "null", "None", True, {}, " x ", 5)] == [
        "",
        "",
        "",
        "",
        "",
        "",
        "x",
        "5",
    ]
    assert hosts_of(None) == []


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("GÃ©nÃ©rique", "Générique"),  # encoded twice by the box
        ("Générique", "Générique"),  # already correct
        ("Salon — TV", "Salon — TV"),  # not latin-1
        ("iPhone", "iPhone"),
    ],
)
def test_fix_text(text: str, expected: str) -> None:
    assert fix_text(text) == expected
    assert clean(f" {text} ") == expected


def test_host_name_repairs_double_encoding() -> None:
    host = {"informations": {"manufacturer": "GÃ©nÃ©rique", "model": "TÃ©lÃ©"}}
    assert host_name(host) == "Générique Télé"
    assert host_name({"hostname": "CafÃ©"}) == "Café"
    assert hosts_of({"devices": {"hosts": {"list": [{"a": 1}, "x"]}}}) == [{"a": 1}]
    assert hosts_of({"devices": {}}) == []


def test_tracked_macs() -> None:
    assert tracked_macs({}) == []
    assert tracked_macs({"tracked_devices": "AA"}) == []
    assert tracked_macs({"tracked_devices": ["AA", "aa", "", None, "bb"]}) == [
        "AA",
        "bb",
    ]


def test_labels_english_and_french() -> None:
    """State and link in the language of Home Assistant (fr, else English)."""
    laptop = HOSTS[0]
    assert host_label(laptop, "L", "en") == "L — online, Wi-Fi 5 GHz"
    assert host_label(laptop, "L", "fr-FR") == "L — en ligne, Wi-Fi 5 GHz"
    assert host_label(laptop, "L", "de") == "L — online, Wi-Fi 5 GHz"
    assert host_label(laptop, "L", None) == "L — online, Wi-Fi 5 GHz"
    offline = HOSTS[2]
    assert host_label(offline, "O", "fr") == "O — hors ligne"
    wired = HOSTS[3]
    assert host_label(wired, "W", "en") == "W — online, Ethernet"
    # Wi-Fi without usable band, band read from the link, comma, unknown link
    nobands = {"active": 1, "link": "Wifi", "wireless": {"band": "N/A"}}
    assert host_label(nobands, "N", "en") == "N — online, Wi-Fi"
    assert host_label({**nobands, "link": "Wifi 5"}, "N", "en").endswith("5 GHz")
    assert host_label({**nobands, "wireless": {"band": "2,4"}}, "N", "en").endswith(
        "Wi-Fi 2.4 GHz"
    )
    assert host_label({**nobands, "link": "Wifi", "wireless": None}, "N", "en")
    assert host_label({"active": 0, "link": "Powerline"}, "N", "en") == "N — offline"
    assert host_label({"active": True}, "N", "en") == "N — online"


def test_options_order_and_unknown() -> None:
    """Active first, then by name; a chosen MAC no longer listed stays proposed."""
    options = device_options(HOSTS, [mac(7), "02:00:00:00:00:FF"], "en")
    macs = [m for m, _ in options]
    labels = dict(options)
    # 6 active hosts first (by name, case insensitive), then the 8 others
    assert macs[:6] == [mac(2), mac(4), mac(11), mac(12), mac(8), mac(1)]
    assert {mac(1), mac(2), mac(4), mac(8), mac(11), mac(12)} == set(macs[:6])
    assert len(options) == 14
    assert labels["02:00:00:00:00:FF"] == "Unknown device (00FF)"
    assert labels[mac(7)] == "Living room TV — offline"
    assert labels[mac(5)] == "Printer — offline, Ethernet"
    assert dict(device_options([], ["aa:bb"], "fr")) == {
        "aa:bb": "Appareil inconnu (AABB)"
    }
    # a host without MAC or repeated is ignored
    assert len(device_options([*HOSTS, HOSTS[0], {"hostname": "x"}], [], "en")) == 13
