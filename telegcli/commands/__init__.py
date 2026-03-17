"""
telegcli.commands
──────────────
Central command dispatch table.
Maps every REPL command name → its async handler.
"""

from telegcli.commands.messages import (
    cmd_read, cmd_send, cmd_reply, cmd_edit,
    cmd_delete, cmd_forward, cmd_react, cmd_pin, cmd_unpin,
    cmd_copy, cmd_thread,
)
from telegcli.commands.chats import (
    cmd_list, cmd_info, cmd_search_chats, cmd_gsearch,
    cmd_mute, cmd_unmute, cmd_archive, cmd_markread,
    cmd_stats, cmd_export, cmd_gallery,
)
from telegcli.commands.files import cmd_upload, cmd_download
from telegcli.commands.watch import cmd_watch
from telegcli.commands.contacts import (
    cmd_contacts, cmd_add_contact, cmd_block, cmd_unblock,
)
from telegcli.commands.misc import (
    cmd_me, cmd_schedule, cmd_automate, cmd_template, cmd_draft,
    cmd_sessions, cmd_theme, cmd_config, cmd_logout, cmd_clear, cmd_help,
)

DISPATCH: dict = {
    # ── Messages ──────────────────────────────────────────────────────
    "read":      cmd_read,
    "send":      cmd_send,
    "reply":     cmd_reply,
    "edit":      cmd_edit,
    "delete":    cmd_delete,
    "forward":   cmd_forward,
    "react":     cmd_react,
    "pin":       cmd_pin,
    "unpin":     cmd_unpin,
    "copy":      cmd_copy,
    "thread":    cmd_thread,

    # ── Chats ─────────────────────────────────────────────────────────
    "list":      cmd_list,
    "info":      cmd_info,
    "search":    cmd_search_chats,
    "gsearch":   cmd_gsearch,
    "mute":      cmd_mute,
    "unmute":    cmd_unmute,
    "archive":   cmd_archive,
    "markread":  cmd_markread,
    "stats":     cmd_stats,
    "export":    cmd_export,
    "gallery":   cmd_gallery,

    # ── Files ─────────────────────────────────────────────────────────
    "upload":    cmd_upload,
    "download":  cmd_download,

    # ── Live ──────────────────────────────────────────────────────────
    "watch":     cmd_watch,

    # ── Contacts ──────────────────────────────────────────────────────
    "contacts":  cmd_contacts,
    "add":       cmd_add_contact,
    "block":     cmd_block,
    "unblock":   cmd_unblock,

    # ── Productivity ──────────────────────────────────────────────────
    "schedule":  cmd_schedule,
    "automate":  cmd_automate,
    "template":  cmd_template,
    "draft":     cmd_draft,

    # ── Sessions ──────────────────────────────────────────────────────
    "sessions":  cmd_sessions,

    # ── Utility ───────────────────────────────────────────────────────
    "me":        cmd_me,
    "theme":     cmd_theme,
    "config":    cmd_config,
    "logout":    cmd_logout,
    "clear":     cmd_clear,
    "help":      cmd_help,
    "?":         cmd_help,
}
