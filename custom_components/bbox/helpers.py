"""Helpers for component."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import format_mac


def finditem(data: dict[str, Any], key_chain: str, default: Any = None) -> Any:
    """Get recursive key and return value.

    data is a mandatory dictionary
    key , string with dot for key delimited (ex: "key.key.key")

    It is possible to integrate an element of an array by indicating its index number
    {"a":{"b":[{"c":"value"}]}
    key = a.b.0.c
    """
    if (keys := key_chain.split(".")) and isinstance(keys, list):
        for key in keys:
            if isinstance(data, dict):
                data = data.get(key)
            elif (
                isinstance(data, list)
                and len(data) > 0
                and key.isdigit()
                and int(key) < len(data)
            ):
                data = data[int(key)]
    return default if data is None and default is not None else data


def box_identifier(lan_ip: Any) -> str | None:
    """Return the identifier of the box: its LAN MAC address, normalized.

    Read from `lan/ip` (public): the same with or without password.
    """
    if isinstance(lan_ip, list) and lan_ip and isinstance(lan_ip[0], dict):
        lan_ip = lan_ip[0]
    if not isinstance(lan_ip, dict):
        return None
    mac = finditem(lan_ip, "lan.ip.mac")
    return format_mac(str(mac)) if mac else None


def host_device_key(box_id: str, mac: str) -> str:
    """Return the key of a host: `{box_id}_{mac}`, the MAC with `_` for `:`.

    The device identifier is `(DOMAIN, key)`; it never changes, whatever the
    name of the host.
    """
    return f"{box_id}_{mac.replace(':', '_')}"
