"""Hash and Base64 helpers (stdlib; size-capped)."""

from __future__ import annotations

import base64
import binascii
import hashlib

MAX_TOOLKIT_INPUT_CHARS = 12_000


def clip_input(text: str) -> tuple[str, bool]:
    t = text or ""
    if len(t) <= MAX_TOOLKIT_INPUT_CHARS:
        return t, False
    return t[:MAX_TOOLKIT_INPUT_CHARS], True


def md5_hex(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def b64_encode_str(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def b64_decode_str(text: str) -> tuple[bool, str]:
    raw = (text or "").strip()
    if not raw:
        return False, "empty"
    try:
        out = base64.b64decode(raw, validate=True)
    except binascii.Error:
        try:
            pad = (-len(raw)) % 4
            out = base64.b64decode(raw + ("=" * pad), validate=False)
        except (binascii.Error, Exception) as e:
            return False, str(e)
    try:
        return True, out.decode("utf-8")
    except UnicodeDecodeError:
        hx = out.hex()
        if len(hx) > 400:
            hx = hx[:400] + "…"
        return True, f"(not utf-8, {len(out)} bytes) {hx}"


def payload_after_command(message_text: str) -> str:
    t = (message_text or "").strip()
    if not t:
        return ""
    parts = t.split(maxsplit=1)
    if len(parts) < 2:
        return ""
    return parts[1]
