"""HTTP / link side of the transfer contract; downloads still run inside ``rub.py`` until cutover."""

from __future__ import annotations

from typing import Any


class HttpLinkTransferAdapter:
    """Placeholder for link→file / URL fetch; worker ``download_url`` remains authoritative."""

    def validate_account(self, user_ctx: dict) -> bool:
        return True

    def healthcheck(self) -> tuple[bool, str]:
        return True, "http_link_stub"

    def resolve_source(self, task: dict) -> Any:
        src = task.get("source") if isinstance(task.get("source"), dict) else {}
        return src.get("ref") or task.get("url")

    def download(self, source_ref: Any, tmp_path: str) -> dict:
        return {
            "ok": False,
            "provider_id": "http",
            "reason": "legacy_worker_path",
            "checksum": "",
            "size_bytes": 0,
            "metadata": {"source_ref": source_ref, "tmp_path": tmp_path},
        }

    def upload(self, local_path: str, destination_ref: Any) -> dict:
        return {
            "ok": False,
            "provider_id": "http",
            "reason": "legacy_worker_path",
            "checksum": "",
            "size_bytes": 0,
            "metadata": {"local_path": local_path, "destination_ref": destination_ref},
        }
