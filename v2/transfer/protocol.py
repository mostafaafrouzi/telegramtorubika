"""Transfer adapter contract (``docs/v2/05-transfer-adapters-spec.md`` §3)."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class TransferAdapter(Protocol):
    """Core methods; optional ``list_files`` / ``delete`` are provider-specific extensions."""

    def validate_account(self, user_ctx: dict) -> bool:
        """Return True if the user can use this provider."""
        ...

    def healthcheck(self) -> tuple[bool, str]:
        """Connectivity / credential sanity check."""
        ...

    def resolve_source(self, task: dict) -> Any:
        """Map task ``source`` to an internal ref for download."""
        ...

    def download(self, source_ref: Any, tmp_path: str) -> dict:
        """Write bytes to ``tmp_path``; return standard metadata dict."""
        ...

    def upload(self, local_path: str, destination_ref: Any) -> dict:
        """Send file; return metadata dict."""
        ...
