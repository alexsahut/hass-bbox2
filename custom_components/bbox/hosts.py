"""Hosts known by the Bbox: readable names, labels and tracked selection."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any

from .const import CONF_TRACKED_DEVICES

# `informations.type` / `devicetype` value which says nothing about the device
GENERIC_TYPES = {"device"}
_NO_VALUE = {"none", "null"}
_BAND = re.compile(r"(\d+(?:[.,]\d+)?)")

_TEXTS = {
    "fr": {
        "online": "en ligne",
        "offline": "hors ligne",
        "unknown": "Appareil inconnu",
        "wifi": "Wi-Fi",
        "ethernet": "Ethernet",
    },
    "en": {
        "online": "online",
        "offline": "offline",
        "unknown": "Unknown device",
        "wifi": "Wi-Fi",
        "ethernet": "Ethernet",
    },
}


def fix_text(text: str) -> str:
    """Return the text decoded once more when the box encoded it twice.

    The box returns some texts encoded twice in UTF-8 ("GÃ©nÃ©rique"): when
    the text, encoded in latin-1, is valid UTF-8, the decoded text is returned
    ("Générique"); otherwise the text is returned unchanged.
    """
    try:
        return text.encode("latin-1").decode("utf-8")
    except UnicodeError:
        return text


def clean(value: Any) -> str:
    """Return the text of a value, "" when it is empty, blank, null or None."""
    if value is None or isinstance(value, bool | dict | list):
        return ""
    text = fix_text(str(value).strip())
    return "" if text.casefold() in _NO_VALUE else text


def hosts_of(data: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    """Return the hosts of the coordinator data (empty when not read)."""
    hosts = ((data or {}).get("devices") or {}).get("hosts") or {}
    return [h for h in hosts.get("list") or [] if isinstance(h, dict)]


def mac_key(mac: Any) -> str:
    """Return the key (lower case) to compare two MAC addresses."""
    return str(mac).strip().lower()


def mac_suffix(mac: str) -> str:
    """Return the 4 last hexadecimal characters of a MAC address, upper case."""
    return re.sub(r"[^0-9a-fA-F]", "", mac)[-4:].upper()


def _generic(value: str) -> bool:
    return value.casefold() in GENERIC_TYPES


def host_name(host: Mapping[str, Any]) -> str:
    """Return the name of a host, without the duplicates handling.

    Order: `userfriendlyname`, `hostname`, "manufacturer model", the type
    (`informations.type`, then `devicetype`, never the generic "Device"), and
    the MAC address only as a last resort.
    """
    for key in ("userfriendlyname", "hostname"):
        if name := clean(host.get(key)):
            return name
    info = host.get("informations")
    info = info if isinstance(info, Mapping) else {}
    if name := " ".join(
        part
        for part in (clean(info.get("manufacturer")), clean(info.get("model")))
        if part
    ):
        return name
    for kind in (clean(info.get("type")), clean(host.get("devicetype"))):
        if kind and not _generic(kind):
            return kind
    return clean(host.get("macaddress"))


def host_names(hosts: Iterable[Mapping[str, Any]]) -> dict[str, str]:
    """Return the name of every host (key: lower case MAC address).

    Hosts of the same name (all the known hosts, not only the tracked ones) get
    the last 4 hexadecimal characters of their MAC address, e.g. "Phone (A1B2)".
    """
    names: dict[str, str] = {}
    macs: dict[str, str] = {}
    for host in hosts:
        if (mac := clean(host.get("macaddress"))) and mac_key(mac) not in names:
            names[mac_key(mac)] = host_name(host)
            macs[mac_key(mac)] = mac
    counts: dict[str, int] = {}
    for name in names.values():
        counts[name.casefold()] = counts.get(name.casefold(), 0) + 1
    return {
        key: f"{name} ({mac_suffix(macs[key])})"
        if counts[name.casefold()] > 1
        else name
        for key, name in names.items()
    }


def tracked_macs(options: Mapping[str, Any]) -> list[str]:
    """Return the MAC addresses chosen in the options (no duplicate, in order)."""
    chosen = options.get(CONF_TRACKED_DEVICES)
    if not isinstance(chosen, list | tuple):
        return []
    result: dict[str, str] = {}
    for mac in chosen:
        if clean(mac):
            result.setdefault(mac_key(mac), clean(mac))
    return list(result.values())


def _texts(language: str | None) -> dict[str, str]:
    return _TEXTS["fr" if (language or "").lower().startswith("fr") else "en"]


def _link_label(host: Mapping[str, Any], texts: dict[str, str]) -> str:
    link = clean(host.get("link"))
    if link.casefold().startswith("eth"):
        return texts["ethernet"]
    if not link.casefold().startswith(("wifi", "wi-fi")):
        return ""
    wireless = host.get("wireless")
    wireless = wireless if isinstance(wireless, Mapping) else {}
    # The band: `wireless.band`, else the end of the link ("Wifi 5")
    for source in (clean(wireless.get("band")), link):
        if match := _BAND.search(source):
            band = float(match.group(1).replace(",", "."))
            return f"{texts['wifi']} {band:g} GHz"
    return texts["wifi"]


def host_label(host: Mapping[str, Any], name: str, language: str | None) -> str:
    """Return the option label: name, state, link (in French if language is fr)."""
    texts = _texts(language)
    state = texts["online"] if host.get("active") in (1, True) else texts["offline"]
    parts = [state, _link_label(host, texts)]
    return f"{name} — {', '.join(part for part in parts if part)}"


def device_options(
    hosts: Iterable[Mapping[str, Any]],
    selected: Iterable[str],
    language: str | None,
) -> list[tuple[str, str]]:
    """Return the (MAC, label) options: active first, then by name.

    A MAC address already chosen but absent from `hosts` stays proposed, as
    unknown, so that saving the options does not lose it.
    """
    hosts = list(hosts)
    names = host_names(hosts)
    rows: dict[str, tuple[bool, str, str, str]] = {}
    for host in hosts:
        if not (mac := clean(host.get("macaddress"))) or mac_key(mac) in rows:
            continue
        name = names[mac_key(mac)]
        active = host.get("active") in (1, True)
        rows[mac_key(mac)] = (
            not active,
            name.casefold(),
            mac,
            host_label(host, name, language),
        )
    for mac in selected:
        if mac_key(mac) not in rows:
            label = f"{_texts(language)['unknown']} ({mac_suffix(mac)})"
            rows[mac_key(mac)] = (True, label.casefold(), mac, label)
    return [(row[2], row[3]) for row in sorted(rows.values())]
