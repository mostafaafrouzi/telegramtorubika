"""Transfer task shape (``docs/v2/05-transfer-adapters-spec.md`` §2) — aligned with existing queue payloads."""

from __future__ import annotations

from typing import Any, TypedDict


class TransferSource(TypedDict, total=False):
    provider: str
    ref: Any


class TransferDestination(TypedDict, total=False):
    provider: str
    ref: Any


class TransferOptions(TypedDict, total=False):
    zip: bool
    unzip: bool
    split_mb: int
    password: str | None
    overwrite: bool


class TransferTaskPayload(TypedDict, total=False):
    """Logical v2 envelope; queue tasks often flatten fields (``rubika_session``, ``path``, …)."""

    task_id: str
    telegram_user_id: int
    plugin: str
    action: str
    source: TransferSource
    destination: TransferDestination
    options: TransferOptions


ACTION_UPLOAD = "upload"
ACTION_DOWNLOAD = "download"
ACTION_BRIDGE = "bridge"
ACTION_CONVERT = "convert"

PROVIDER_TELEGRAM = "telegram"
PROVIDER_RUBIKA = "rubika"
PROVIDER_HTTP = "http"
PROVIDER_BALE = "bale"
PROVIDER_DRIVE = "drive"
