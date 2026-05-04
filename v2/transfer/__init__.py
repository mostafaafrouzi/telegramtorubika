"""Transfer stack adapters (see ``docs/v2/05-transfer-adapters-spec.md``)."""

from . import task_model
from .integration import validate_transfer_task_v2
from .link_adapter import HttpLinkTransferAdapter
from .protocol import TransferAdapter
from .rubika_adapter import RubikaTransferAdapter

__all__ = [
    "HttpLinkTransferAdapter",
    "RubikaTransferAdapter",
    "TransferAdapter",
    "task_model",
    "validate_transfer_task_v2",
]
