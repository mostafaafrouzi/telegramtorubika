"""Wave-1 network tool: hostname → IP list (stdlib only)."""

from __future__ import annotations

import re
import socket

_HOST_ASCII = re.compile(r"^[a-zA-Z0-9.\-]{1,253}$")


def normalized_toolkit_host(hostname: str) -> str | None:
    """ASCII hostname/IP label safe for toolkit commands; ``None`` if invalid."""
    h = (hostname or "").strip().lower()
    if not h or not _HOST_ASCII.match(h):
        return None
    if h.startswith(".") or ".." in h or h.endswith("."):
        return None
    return h


def resolve_hostname(hostname: str) -> tuple[bool, str]:
    """Resolve A/AAAA records via ``getaddrinfo``. Returns ``(ok, message_or_ips)``."""
    h = normalized_toolkit_host(hostname)
    if not h:
        return False, "invalid_hostname"
    try:
        infos = socket.getaddrinfo(h, None, type=socket.SOCK_STREAM)
    except socket.gaierror as e:
        return False, str(e)
    ips = sorted({addr[4][0] for addr in infos})
    if not ips:
        return True, "—"
    return True, "\n".join(ips)
