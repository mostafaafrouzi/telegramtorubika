"""Outbound public IPv4 via ipify (HTTPS)."""

from __future__ import annotations

import urllib.request


def get_public_ip(*, timeout: float = 8.0) -> tuple[bool, str]:
    try:
        req = urllib.request.Request(
            "https://api.ipify.org",
            headers={"User-Agent": "telegramtorubika-toolkit/1"},
        )
        with urllib.request.urlopen(req, timeout=float(timeout)) as r:
            body = r.read().decode("ascii", errors="replace").strip()
            return True, body
    except Exception as e:
        return False, str(e)
