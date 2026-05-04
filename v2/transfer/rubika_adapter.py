"""Rubika side of the transfer contract; heavy upload/download still use ``rub.py`` worker until cutover."""

from __future__ import annotations

from typing import Any, Callable, Optional

from v2.transfer.protocol import TransferAdapter


class RubikaTransferAdapter:
    """Session-aware adapter: validate/resolve/healthcheck are real; file IO defers to legacy worker."""

    def __init__(
        self,
        get_rubika_session: Callable[[int], Optional[str]],
        *,
        check_session_sync: Optional[Callable[[str], tuple[bool, str]]] = None,
        probe_session_name: Optional[str] = None,
    ) -> None:
        self._get_session = get_rubika_session
        self._check_session = check_session_sync
        self._probe_session_name = (probe_session_name or "").strip() or None

    def validate_account(self, user_ctx: dict) -> bool:
        uid = user_ctx.get("telegram_user_id")
        if uid is None:
            return False
        return bool((self._get_session(int(uid)) or "").strip())

    def healthcheck(self) -> tuple[bool, str]:
        if self._check_session and self._probe_session_name:
            return self._check_session(self._probe_session_name)
        if self._check_session is None:
            return True, "no_sync_probe_configured"
        return True, "probe_session_name_unset"

    def resolve_source(self, task: dict) -> Any:
        src = task.get("source") if isinstance(task.get("source"), dict) else {}
        return src.get("ref")

    def download(self, source_ref: Any, tmp_path: str) -> dict:
        return {
            "ok": False,
            "provider_id": "rubika",
            "reason": "legacy_worker_path",
            "checksum": "",
            "size_bytes": 0,
            "metadata": {"source_ref": source_ref, "tmp_path": tmp_path},
        }

    def upload(self, local_path: str, destination_ref: Any) -> dict:
        return {
            "ok": False,
            "provider_id": "rubika",
            "reason": "legacy_worker_path",
            "checksum": "",
            "size_bytes": 0,
            "metadata": {"local_path": local_path, "destination_ref": destination_ref},
        }

    def probe_session(self, session_name: str) -> tuple[bool, str]:
        """Optional explicit connectivity check when ``check_session_sync`` was injected."""
        if not self._check_session:
            return False, "no_check_session_sync"
        return self._check_session(session_name)
