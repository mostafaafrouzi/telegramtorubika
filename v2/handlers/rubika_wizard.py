"""Rubika phone login wizard: await_phone -> await_pass_key? -> await_code -> save session."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Optional

from pyrogram.types import Message

TranslateFn = Callable[[int, str], str]
AsyncSendCode = Callable[..., Awaitable[Any]]
AsyncSignIn = Callable[..., Awaitable[Any]]


@dataclass(frozen=True)
class RubikaWizardDeps:
    tr: TranslateFn
    set_state_preserving_menu: Callable[..., None]
    clear_state: Callable[[int], None]
    get_user_key: Callable[[int], str]
    load_users: Callable[[], Dict[str, Any]]
    save_users: Callable[[Dict[str, Any]], None]
    log_event: Callable[..., None]
    persist_rubika_session: Callable[[int, str], None]
    rubika_send_code: AsyncSendCode
    rubika_sign_in: AsyncSignIn
    deep_find_phone_hash: Callable[[Any], Optional[str]]
    deep_find_status: Callable[[Any], str]


async def dispatch_rubika_connect_wizard(
    message: Message,
    user_id: int,
    state: dict,
    text: str,
    deps: RubikaWizardDeps,
) -> bool:
    """
    Handle Rubika connect multi-step text flow.
    Returns True if this message was consumed by the wizard.
    """
    tr = deps.tr
    step = state.get("step")
    if step == "await_phone":
        phone = text.strip().replace("+", "")
        session_name = f"rubika_{user_id}"
        try:
            result = await deps.rubika_send_code(session_name, phone)
            phone_hash = deps.deep_find_phone_hash(result)
            status = deps.deep_find_status(result).upper()
            if status == "SENDPASSKEY":
                deps.set_state_preserving_menu(
                    user_id,
                    {
                        "step": "await_pass_key",
                        "session_name": session_name,
                        "phone_number": phone,
                    },
                )
                await message.reply_text(tr(user_id, "rubika_passkey_needed"))
                return True
            if not phone_hash:
                raise RuntimeError(f"phone_code_hash پیدا نشد. status={status or 'unknown'}")
            deps.set_state_preserving_menu(
                user_id,
                {
                    "step": "await_code",
                    "session_name": session_name,
                    "phone_number": phone,
                    "phone_code_hash": phone_hash,
                },
            )
            await message.reply_text(tr(user_id, "rubika_code_sent"))
        except Exception as e:
            deps.clear_state(user_id)
            await message.reply_text(tr(user_id, "rubika_send_code_error", error=str(e)))
        return True

    if step == "await_pass_key":
        pass_key = text.strip()
        session_name = state.get("session_name", "")
        phone_number = state.get("phone_number", "")
        try:
            result = await deps.rubika_send_code(session_name, phone_number, pass_key=pass_key)
            phone_hash = deps.deep_find_phone_hash(result)
            status = deps.deep_find_status(result).upper()
            if not phone_hash:
                raise RuntimeError(f"phone_code_hash پیدا نشد. status={status or 'unknown'}")
            deps.set_state_preserving_menu(
                user_id,
                {
                    "step": "await_code",
                    "session_name": session_name,
                    "phone_number": phone_number,
                    "phone_code_hash": phone_hash,
                },
            )
            await message.reply_text(tr(user_id, "rubika_code_sent"))
        except Exception as e:
            deps.clear_state(user_id)
            await message.reply_text(tr(user_id, "rubika_send_code_error", error=str(e)))
        return True

    if step == "await_code":
        code = text.strip()
        session_name = state.get("session_name", "")
        phone_number = state.get("phone_number", "")
        phone_code_hash = state.get("phone_code_hash", "")
        try:
            await deps.rubika_sign_in(session_name, phone_number, phone_code_hash, code)
            users = deps.load_users()
            key = deps.get_user_key(user_id)
            prev = users.get(key, {})
            users[key] = {
                **prev,
                "connected": True,
                "session": session_name,
                "phone_number": phone_number,
                "connected_at": int(time.time()),
            }
            deps.save_users(users)
            deps.persist_rubika_session(user_id, session_name)
            deps.clear_state(user_id)
            await message.reply_text(tr(user_id, "rubika_connected_ok"))
            deps.log_event("rubika_connect_ok", user_id=user_id, session=session_name)
        except Exception as e:
            deps.clear_state(user_id)
            deps.log_event("rubika_connect_failed", user_id=user_id, error=str(e))
            await message.reply_text(tr(user_id, "rubika_bad_code", error=str(e)))
        return True

    return False
