"""Telegram bot handlers extracted incrementally from legacy monolith."""

from v2.handlers.reply_routes import ReplyRouteDeps, dispatch_reply_keyboard_route
from v2.handlers.rubika_wizard import RubikaWizardDeps, dispatch_rubika_connect_wizard
from v2.handlers.zip_batch_wizard import ZipBatchWizardDeps, dispatch_zip_batch_wizard
from v2.handlers.zip_password_prompt import ZipPasswordPromptDeps, handle_zip_password_text
from v2.handlers.direct_mode_text import DirectModeTextDeps, handle_direct_mode_plain_text
from v2.handlers.direct_url_hint import DirectUrlHintDeps, handle_direct_url_sendlink_hint
from v2.handlers.admin_commands import (
    AdminCommandDeps,
    handle_admin_bonus,
    handle_admin_panel,
    handle_admin_payment_lookup,
    handle_admin_payment_status,
    handle_admin_reconcile_billing,
    handle_admin_tier,
    handle_cleanup_downloads,
)
from v2.handlers.plan_commands import PlanCommandDeps, handle_plan, handle_purchase, handle_usage
from v2.handlers.queue_commands import (
    QueueCommandDeps,
    handle_clear_queue,
    handle_queue_manage,
    handle_send_link,
    handle_send_text,
)
from v2.handlers.safemode_command import SafeModeCommandDeps, handle_safemode
from v2.handlers.delete_command import DeleteCommandDeps, handle_delete_one
from v2.handlers.callback_routes import CallbackRouteDeps, dispatch_callback_route
from v2.handlers.batch_commands import BatchCommandDeps, handle_done_batch, handle_new_batch
from v2.handlers.text_entry import TextEntryDeps, handle_text_entry
from v2.handlers.toolkit_commands import (
    ToolkitCommandDeps,
    handle_b64_decode,
    handle_b64_encode,
    handle_dns_lookup,
    handle_md5,
    handle_my_ip,
    handle_sha256,
    handle_tcp_ping,
)
from v2.handlers.media_handler import MediaHandlerDeps, handle_media_message
from v2.handlers.session_settings_commands import (
    SessionSettingsCommandDeps,
    handle_direct_mode,
    handle_netstatus,
    handle_rubika_connect,
    handle_rubika_status,
)
from v2.handlers.basic_commands import (
    BasicCommandDeps,
    handle_help,
    handle_lang,
    handle_log_help,
    handle_menu,
    handle_start,
    handle_version,
)

__all__ = [
    "ReplyRouteDeps",
    "dispatch_reply_keyboard_route",
    "RubikaWizardDeps",
    "dispatch_rubika_connect_wizard",
    "ZipBatchWizardDeps",
    "dispatch_zip_batch_wizard",
    "ZipPasswordPromptDeps",
    "handle_zip_password_text",
    "DirectModeTextDeps",
    "handle_direct_mode_plain_text",
    "DirectUrlHintDeps",
    "handle_direct_url_sendlink_hint",
    "BasicCommandDeps",
    "handle_start",
    "handle_menu",
    "handle_lang",
    "handle_help",
    "handle_log_help",
    "handle_version",
    "SessionSettingsCommandDeps",
    "handle_rubika_status",
    "handle_rubika_connect",
    "handle_direct_mode",
    "handle_netstatus",
    "PlanCommandDeps",
    "handle_usage",
    "handle_plan",
    "handle_purchase",
    "AdminCommandDeps",
    "handle_admin_panel",
    "handle_admin_tier",
    "handle_admin_bonus",
    "handle_admin_payment_lookup",
    "handle_admin_payment_status",
    "handle_admin_reconcile_billing",
    "handle_cleanup_downloads",
    "QueueCommandDeps",
    "handle_send_text",
    "handle_send_link",
    "handle_queue_manage",
    "handle_clear_queue",
    "SafeModeCommandDeps",
    "handle_safemode",
    "DeleteCommandDeps",
    "handle_delete_one",
    "CallbackRouteDeps",
    "dispatch_callback_route",
    "BatchCommandDeps",
    "handle_new_batch",
    "handle_done_batch",
    "TextEntryDeps",
    "handle_text_entry",
    "ToolkitCommandDeps",
    "handle_dns_lookup",
    "handle_my_ip",
    "handle_tcp_ping",
    "handle_md5",
    "handle_sha256",
    "handle_b64_encode",
    "handle_b64_decode",
    "MediaHandlerDeps",
    "handle_media_message",
]
