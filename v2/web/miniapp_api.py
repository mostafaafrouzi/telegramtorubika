"""JSON API for Telegram Mini App (server-side tools that need no browser CORS)."""

from __future__ import annotations

import json
import os
import time
import urllib.parse
from collections import defaultdict, deque
from typing import Any

from v2.toolkit.dns_light import resolve_hostname
from v2.toolkit.net_extra_light import (
    http_headers_report,
    port_check_report,
    ssl_cert_report,
    website_status_report,
)
from v2.toolkit.ping_light import smart_tcp_ping
from v2.toolkit.whois_light import rdap_lookup
from v2.web.telegram_webapp_auth import validate_init_data

_RATE: dict[str, deque[float]] = defaultdict(deque)
_RATE_LIMIT = 30
_RATE_WINDOW = 60.0


def _q(params: dict[str, list[str]], key: str) -> str:
    vals = params.get(key) or [""]
    return (vals[0] if vals else "").strip()


def _json_response(
    ok: bool,
    *,
    text: str = "",
    error: str = "",
    http: int | None = None,
    data: Any = None,
) -> tuple[int, bytes]:
    body: dict[str, Any] = {"ok": ok}
    if ok:
        if text:
            body["text"] = text
        if data is not None:
            body["data"] = data
    else:
        body["error"] = error or text or "error"
    raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
    if http is not None:
        return http, raw
    return 200 if ok else 400, raw


def _rate_ok(bucket: str) -> bool:
    now = time.time()
    q = _RATE[bucket]
    while q and now - q[0] > _RATE_WINDOW:
        q.popleft()
    if len(q) >= _RATE_LIMIT:
        return False
    q.append(now)
    return True


def _auth_ok(params: dict[str, list[str]]) -> tuple[bool, str]:
    """Require Telegram initData unless MINIAPP_API_OPEN=1 (dev only)."""
    open_mode = (os.getenv("MINIAPP_API_OPEN") or "").strip().lower() in ("1", "true", "yes")
    if open_mode:
        return True, "open"
    init_data = _q(params, "initData") or _q(params, "init_data")
    ok, payload = validate_init_data(init_data)
    if not ok:
        return False, str(payload.get("error") or "unauthorized")
    user = payload.get("user") or {}
    uid = str(user.get("id") or "anon")
    if not _rate_ok(uid):
        return False, "rate_limited"
    return True, uid


def dispatch_miniapp_api(path: str, query_string: str) -> tuple[int, str, bytes]:
    """
    Handle ``/miniapp/api/<action>?...``.

    Returns ``(http_status, content_type, body_bytes)``.
    """
    sub = (path or "").strip("/")
    prefix = "miniapp/api/"
    if sub.startswith(prefix):
        action = sub[len(prefix) :].split("/")[0].lower()
    else:
        action = sub.split("/")[-1].lower() if "/api/" in sub else ""

    params = urllib.parse.parse_qs(query_string or "", keep_blank_values=False)

    auth_ok, auth_detail = _auth_ok(params)
    if not auth_ok:
        code = 429 if auth_detail == "rate_limited" else 401
        status, body = _json_response(False, error=auth_detail, http=code)
        return status, "application/json; charset=utf-8", body

    if action == "headers":
        url = _q(params, "url")
        if not url:
            status, body = _json_response(False, error="missing_url")
            return status, "application/json; charset=utf-8", body
        ok, detail = http_headers_report(url)
        status, body = _json_response(ok, text=detail if ok else "", error=detail if not ok else "")
        return status, "application/json; charset=utf-8", body

    if action == "status":
        url = _q(params, "url")
        if not url:
            status, body = _json_response(False, error="missing_url")
            return status, "application/json; charset=utf-8", body
        ok, detail = website_status_report(url)
        status, body = _json_response(ok, text=detail if ok else "", error=detail if not ok else "")
        return status, "application/json; charset=utf-8", body

    if action == "whois":
        query = _q(params, "q") or _q(params, "url") or _q(params, "host")
        if not query:
            status, body = _json_response(False, error="missing_query")
            return status, "application/json; charset=utf-8", body
        ok, detail = rdap_lookup(query)
        status, body = _json_response(ok, text=detail if ok else "", error=detail if not ok else "")
        return status, "application/json; charset=utf-8", body

    if action == "ping":
        host = _q(params, "host") or _q(params, "q")
        if not host:
            status, body = _json_response(False, error="missing_host")
            return status, "application/json; charset=utf-8", body
        port_s = _q(params, "port")
        port = int(port_s) if port_s.isdigit() else None
        ok, detail, used = smart_tcp_ping(host, port=port)
        text = f"TCP ping {host}:{used} → {detail} ms" if ok else detail
        status, body = _json_response(ok, text=text if ok else "", error=detail if not ok else "")
        return status, "application/json; charset=utf-8", body

    if action == "port":
        host = _q(params, "host") or _q(params, "q")
        port_s = _q(params, "port")
        if not host or not port_s.isdigit():
            status, body = _json_response(False, error="missing_host_or_port")
            return status, "application/json; charset=utf-8", body
        ok, detail = port_check_report(host, int(port_s))
        status, body = _json_response(ok, text=detail if ok else "", error=detail if not ok else "")
        return status, "application/json; charset=utf-8", body

    if action == "ssl":
        host = _q(params, "host") or _q(params, "q") or _q(params, "domain")
        if not host:
            status, body = _json_response(False, error="missing_host")
            return status, "application/json; charset=utf-8", body
        ok, detail = ssl_cert_report(host)
        status, body = _json_response(ok, text=detail if ok else "", error=detail if not ok else "")
        return status, "application/json; charset=utf-8", body

    if action == "dns":
        host = _q(params, "q") or _q(params, "host") or _q(params, "name")
        if not host:
            status, body = _json_response(False, error="missing_host")
            return status, "application/json; charset=utf-8", body
        # Server-side A/AAAA via getaddrinfo (type param accepted for API symmetry)
        ok, detail = resolve_hostname(host)
        rtype = (_q(params, "type") or "A").upper()
        text = f"{rtype} (server resolve) {host}\n{detail}" if ok else detail
        status, body = _json_response(ok, text=text if ok else "", error=detail if not ok else "")
        return status, "application/json; charset=utf-8", body

    if action.startswith("alerts_"):
        from v2.web.miniapp_alerts_api import handle_alerts_action

        result = handle_alerts_action(
            action,
            q=lambda k: _q(params, k),
            auth_detail=auth_detail,
            json_response=_json_response,
        )
        if result is not None:
            status, body = result
            return status, "application/json; charset=utf-8", body

    err = json.dumps({"ok": False, "error": "unknown_action"}).encode("utf-8")
    return 404, "application/json; charset=utf-8", err
