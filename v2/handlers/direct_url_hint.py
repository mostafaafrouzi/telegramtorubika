"""Hint user to use /sendlink when message looks like a plain HTTP URL in chat."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from pyrogram.types import Message

TranslateFn = Callable[[int, str], str]


@dataclass(frozen=True)
class DirectUrlHintDeps:
    tr: TranslateFn
    extract_first_url: Callable[[str], Optional[str]]
    is_direct_url: Callable[[str], bool]


async def handle_direct_url_sendlink_hint(
    message: Message,
    user_id: int,
    text: str,
    deps: DirectUrlHintDeps,
) -> bool:
    """Returns True when user was shown the sendlink hint."""
    url = deps.extract_first_url(text)
    if not url or not deps.is_direct_url(url):
        return False
    await message.reply_text(deps.tr(user_id, "direct_url_use_sendlink"), parse_mode=None)
    return True
