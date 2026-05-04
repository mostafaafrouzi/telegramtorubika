"""Toolkit slash commands (feature-flagged)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from pyrogram.types import Message

from v2.core.menu_sections import MenuSection
from v2.toolkit.dns_light import resolve_hostname
from v2.toolkit.myip_light import get_public_ip
from v2.toolkit.ping_light import tcp_ping
from v2.toolkit.text_utils_light import (
    b64_decode_str,
    b64_encode_str,
    clip_input,
    md5_hex,
    payload_after_command,
    sha256_hex,
)

TranslateFn = Callable[..., str]


@dataclass(frozen=True)
class ToolkitCommandDeps:
    tr: TranslateFn
    set_menu_section: Callable[[int, MenuSection], None]
    toolkit_network_light_enabled: bool
    toolkit_utility_light_enabled: bool
    toolkit_quota_try: Callable[[int], tuple[bool, str]]
    toolkit_quota_commit: Callable[[int], None]


async def _guard_toolkit_quota_try(deps: ToolkitCommandDeps, message: Message, uid: int) -> bool:
    ok, msg = deps.toolkit_quota_try(uid)
    if not ok:
        await message.reply_text(msg, parse_mode=None)
        return False
    return True


async def handle_dns_lookup(deps: ToolkitCommandDeps, client: Any, message: Message) -> None:
    uid = message.from_user.id
    deps.set_menu_section(uid, MenuSection.MAIN)
    if not deps.toolkit_network_light_enabled:
        await message.reply_text(deps.tr(uid, "toolkit_network_disabled"), parse_mode=None)
        return
    parts = (message.text or "").split()
    if len(parts) < 2:
        await message.reply_text(deps.tr(uid, "toolkit_dns_usage"), parse_mode=None)
        return
    host = parts[1].strip()
    if not await _guard_toolkit_quota_try(deps, message, uid):
        return
    ok, body = resolve_hostname(host)
    if not ok:
        await message.reply_text(
            deps.tr(uid, "toolkit_dns_error", host=host, error=body),
            parse_mode=None,
        )
        return
    deps.toolkit_quota_commit(uid)
    await message.reply_text(
        deps.tr(uid, "toolkit_dns_result", host=host, ips=body),
        parse_mode=None,
    )


async def handle_my_ip(deps: ToolkitCommandDeps, client: Any, message: Message) -> None:
    uid = message.from_user.id
    deps.set_menu_section(uid, MenuSection.MAIN)
    if not deps.toolkit_network_light_enabled:
        await message.reply_text(deps.tr(uid, "toolkit_network_disabled"), parse_mode=None)
        return
    if not await _guard_toolkit_quota_try(deps, message, uid):
        return
    ok, body = get_public_ip()
    if not ok:
        await message.reply_text(deps.tr(uid, "toolkit_myip_error", error=body), parse_mode=None)
        return
    deps.toolkit_quota_commit(uid)
    await message.reply_text(deps.tr(uid, "toolkit_myip_result", ip=body), parse_mode=None)


async def handle_tcp_ping(deps: ToolkitCommandDeps, client: Any, message: Message) -> None:
    uid = message.from_user.id
    deps.set_menu_section(uid, MenuSection.MAIN)
    if not deps.toolkit_network_light_enabled:
        await message.reply_text(deps.tr(uid, "toolkit_network_disabled"), parse_mode=None)
        return
    parts = (message.text or "").split()
    if len(parts) < 2:
        await message.reply_text(deps.tr(uid, "toolkit_ping_usage"), parse_mode=None)
        return
    host = parts[1].strip()
    port = 443
    if len(parts) >= 3:
        try:
            port = int(parts[2].strip())
        except ValueError:
            await message.reply_text(deps.tr(uid, "toolkit_ping_usage"), parse_mode=None)
            return
    if not await _guard_toolkit_quota_try(deps, message, uid):
        return
    ok, body = tcp_ping(host, port=port)
    if not ok:
        await message.reply_text(
            deps.tr(uid, "toolkit_ping_error", host=host, port=port, error=body),
            parse_mode=None,
        )
        return
    deps.toolkit_quota_commit(uid)
    await message.reply_text(
        deps.tr(uid, "toolkit_ping_result", host=host, port=port, ms=body),
        parse_mode=None,
    )


async def handle_md5(deps: ToolkitCommandDeps, client: Any, message: Message) -> None:
    uid = message.from_user.id
    deps.set_menu_section(uid, MenuSection.MAIN)
    if not deps.toolkit_utility_light_enabled:
        await message.reply_text(deps.tr(uid, "toolkit_utility_disabled"), parse_mode=None)
        return
    raw = payload_after_command(message.text or "")
    if not raw.strip():
        await message.reply_text(deps.tr(uid, "toolkit_md5_usage"), parse_mode=None)
        return
    if not await _guard_toolkit_quota_try(deps, message, uid):
        return
    text, trunc = clip_input(raw)
    h = md5_hex(text)
    extra = "\n" + deps.tr(uid, "toolkit_input_truncated") if trunc else ""
    deps.toolkit_quota_commit(uid)
    await message.reply_text(deps.tr(uid, "toolkit_md5_result", digest=h) + extra, parse_mode=None)


async def handle_sha256(deps: ToolkitCommandDeps, client: Any, message: Message) -> None:
    uid = message.from_user.id
    deps.set_menu_section(uid, MenuSection.MAIN)
    if not deps.toolkit_utility_light_enabled:
        await message.reply_text(deps.tr(uid, "toolkit_utility_disabled"), parse_mode=None)
        return
    raw = payload_after_command(message.text or "")
    if not raw.strip():
        await message.reply_text(deps.tr(uid, "toolkit_sha256_usage"), parse_mode=None)
        return
    if not await _guard_toolkit_quota_try(deps, message, uid):
        return
    text, trunc = clip_input(raw)
    h = sha256_hex(text)
    extra = "\n" + deps.tr(uid, "toolkit_input_truncated") if trunc else ""
    deps.toolkit_quota_commit(uid)
    await message.reply_text(deps.tr(uid, "toolkit_sha256_result", digest=h) + extra, parse_mode=None)


async def handle_b64_encode(deps: ToolkitCommandDeps, client: Any, message: Message) -> None:
    uid = message.from_user.id
    deps.set_menu_section(uid, MenuSection.MAIN)
    if not deps.toolkit_utility_light_enabled:
        await message.reply_text(deps.tr(uid, "toolkit_utility_disabled"), parse_mode=None)
        return
    raw = payload_after_command(message.text or "")
    if not raw.strip():
        await message.reply_text(deps.tr(uid, "toolkit_b64e_usage"), parse_mode=None)
        return
    if not await _guard_toolkit_quota_try(deps, message, uid):
        return
    text, trunc = clip_input(raw)
    out = b64_encode_str(text)
    extra = "\n" + deps.tr(uid, "toolkit_input_truncated") if trunc else ""
    deps.toolkit_quota_commit(uid)
    await message.reply_text(deps.tr(uid, "toolkit_b64e_result", data=out) + extra, parse_mode=None)


async def handle_b64_decode(deps: ToolkitCommandDeps, client: Any, message: Message) -> None:
    uid = message.from_user.id
    deps.set_menu_section(uid, MenuSection.MAIN)
    if not deps.toolkit_utility_light_enabled:
        await message.reply_text(deps.tr(uid, "toolkit_utility_disabled"), parse_mode=None)
        return
    raw = payload_after_command(message.text or "")
    if not raw.strip():
        await message.reply_text(deps.tr(uid, "toolkit_b64d_usage"), parse_mode=None)
        return
    if not await _guard_toolkit_quota_try(deps, message, uid):
        return
    text, trunc = clip_input(raw)
    ok, out = b64_decode_str(text)
    if not ok:
        await message.reply_text(deps.tr(uid, "toolkit_b64d_error", error=out), parse_mode=None)
        return
    extra = "\n" + deps.tr(uid, "toolkit_input_truncated") if trunc else ""
    deps.toolkit_quota_commit(uid)
    await message.reply_text(deps.tr(uid, "toolkit_b64d_result", data=out) + extra, parse_mode=None)
