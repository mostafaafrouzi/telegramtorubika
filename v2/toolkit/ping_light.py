"""TCP connect latency to host:port (not ICMP)."""

from __future__ import annotations

import socket
import time

from v2.toolkit.dns_light import normalized_toolkit_host


def tcp_ping(hostname: str, *, port: int = 443, timeout: float = 4.0) -> tuple[bool, str]:
    """Try TCP connection; returns ``(True, "<ms>")`` or ``(False, error)``."""
    h = normalized_toolkit_host(hostname)
    if not h:
        return False, "invalid_hostname"
    p = int(port)
    if not (1 <= p <= 65535):
        return False, "invalid_port"
    t0 = time.time()
    try:
        socket.create_connection((h, p), timeout=float(timeout))
        ms = (time.time() - t0) * 1000
        return True, f"{ms:.0f}"
    except OSError as e:
        return False, str(e)
