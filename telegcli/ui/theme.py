"""
telegcli.ui.theme
──────────────
All visual rendering.  Rich-powered, theme-aware.

Fixes applied:
  #18 — render_messages groups by day with separators; most-recent at bottom
"""

from __future__ import annotations

from datetime import datetime, timezone, date as date_type
from typing import Optional, Any

from rich.console import Console
from rich.theme import Theme
from rich.text import Text
from rich.panel import Panel
from rich.table import Table
from rich.rule import Rule
from rich.align import Align
from rich.style import Style
from rich import box
from telethon.tl.types import User, Chat, Channel, Message

from telegcli.core.config import get_config


# ── Colour palettes ───────────────────────────────────────────────────────────

THEMES = {
    "dark": {
        "bg":         "#1a1b26",
        "fg":         "#c0caf5",
        "dim":        "#565f89",
        "accent":     "#7aa2f7",
        "accent2":    "#bb9af7",
        "success":    "#9ece6a",
        "warning":    "#e0af68",
        "error":      "#f7768e",
        "self_msg":   "#7aa2f7",
        "other_msg":  "#c0caf5",
        "timestamp":  "#565f89",
        "unread":     "#9ece6a",
        "separator":  "#3b4261",
        "header_bg":  "#24283b",
        "selected":   "#2d3f76",
    },
    "gruvbox": {
        "bg":         "#282828",
        "fg":         "#ebdbb2",
        "dim":        "#928374",
        "accent":     "#83a598",
        "accent2":    "#d3869b",
        "success":    "#b8bb26",
        "warning":    "#fabd2f",
        "error":      "#fb4934",
        "self_msg":   "#83a598",
        "other_msg":  "#ebdbb2",
        "timestamp":  "#928374",
        "unread":     "#b8bb26",
        "separator":  "#3c3836",
        "header_bg":  "#32302f",
        "selected":   "#504945",
    },
    "tokyo": {
        "bg":         "#1f2335",
        "fg":         "#a9b1d6",
        "dim":        "#444b6a",
        "accent":     "#7dcfff",
        "accent2":    "#ff9e64",
        "success":    "#73daca",
        "warning":    "#e0af68",
        "error":      "#f7768e",
        "self_msg":   "#7dcfff",
        "other_msg":  "#a9b1d6",
        "timestamp":  "#444b6a",
        "unread":     "#73daca",
        "separator":  "#292e42",
        "header_bg":  "#24283b",
        "selected":   "#2d3f76",
    },
    "light": {
        "bg":         "#fafafa",
        "fg":         "#383a42",
        "dim":        "#9ca0a4",
        "accent":     "#4078f2",
        "accent2":    "#a626a4",
        "success":    "#50a14f",
        "warning":    "#c18401",
        "error":      "#e45649",
        "self_msg":   "#4078f2",
        "other_msg":  "#383a42",
        "timestamp":  "#9ca0a4",
        "unread":     "#50a14f",
        "separator":  "#e5e5e6",
        "header_bg":  "#f0f0f1",
        "selected":   "#d0e3ff",
    },
}


def get_palette() -> dict[str, str]:
    return THEMES.get(get_config().get("theme", "dark"), THEMES["dark"])


def make_rich_theme() -> Theme:
    p = get_palette()
    return Theme({
        "tg.accent":  p["accent"],
        "tg.accent2": p["accent2"],
        "tg.dim":     p["dim"],
        "tg.success": p["success"],
        "tg.warning": p["warning"],
        "tg.error":   p["error"],
        "tg.self":    p["self_msg"],
        "tg.other":   p["other_msg"],
        "tg.ts":      p["timestamp"],
        "tg.unread":  p["unread"],
        "tg.sep":     p["separator"],
        "tg.header":  p["header_bg"],
    })


_console: Console | None = None


def get_console() -> Console:
    global _console
    if _console is None:
        _console = Console(theme=make_rich_theme(), highlight=False)
    return _console


def refresh_console() -> None:
    global _console
    _console = Console(theme=make_rich_theme(), highlight=False)


# ── Entity helpers ────────────────────────────────────────────────────────────

def entity_name(entity) -> str:
    if isinstance(entity, User):
        parts = [entity.first_name or "", entity.last_name or ""]
        return " ".join(p for p in parts if p).strip() or str(entity.id)
    if isinstance(entity, (Chat, Channel)):
        return entity.title or str(entity.id)
    return str(getattr(entity, "id", "?"))


def entity_type_icon(entity) -> str:
    if isinstance(entity, User):
        return "🤖" if getattr(entity, "bot", False) else "👤"
    if isinstance(entity, Channel):
        return "📢" if getattr(entity, "broadcast", False) else "👥"
    if isinstance(entity, Chat):
        return "👥"
    return "💬"


def format_ts(dt: Optional[datetime], fmt: Optional[str] = None) -> str:
    if dt is None:
        return ""
    fmt = fmt or get_config().get("date_format", "%b %d %H:%M")
    return dt.astimezone().strftime(fmt)


def _day_label(dt: datetime) -> str:
    """Return 'Today', 'Yesterday', or formatted date string."""
    local_date = dt.astimezone().date()
    today = datetime.now().date()
    diff = (today - local_date).days
    if diff == 0:
        return "Today"
    if diff == 1:
        return "Yesterday"
    return local_date.strftime("%B %d, %Y")


# ── Dialog list rendering ─────────────────────────────────────────────────────

def render_dialog_list(dialogs: list, selected: int = 0) -> Table:
    p = get_palette()
    table = Table(
        show_header=True,
        header_style=f"bold {p['accent']}",
        box=box.SIMPLE,
        padding=(0, 1),
        expand=True,
    )
    table.add_column("#",    style=p["dim"],       width=4,  no_wrap=True)
    table.add_column("",     width=2,              no_wrap=True)
    table.add_column("Name", style=p["fg"],        ratio=3,  no_wrap=True)
    table.add_column("Last message",               no_wrap=False)
    table.add_column("Time", style=p["timestamp"], width=10, no_wrap=True)
    table.add_column("",     width=4,              no_wrap=True)

    for i, dialog in enumerate(dialogs):
        icon     = entity_type_icon(dialog.entity) if dialog.entity else "💬"
        name     = dialog.name or "(unnamed)"
        ts       = format_ts(dialog.date)
        last_msg = ""
        
        # Show last message + link preview if available
        if dialog.message:
            msg = dialog.message
            if msg.text:
                last_msg = msg.text[:60].replace("\n", " ")
            elif msg.media:
                last_msg = "[media]"
        
        # Feature 16: Add link preview URL if available
        if hasattr(dialog, 'link_preview') and dialog.link_preview:
            if last_msg:
                last_msg += f"\n{Text(dialog.link_preview, style=f'dim italic')}"
            else:
                last_msg = Text(dialog.link_preview, style=f'dim italic')
        
        unread = (
            f"[{p['unread']}]{dialog.unread_count}[/]"
            if dialog.unread_count else ""
        )
        row_style = Style(bgcolor=p["selected"]) if i == selected else Style()
        name_styled = Text(name)
        if dialog.unread_count:
            name_styled.stylize(f"bold {p['fg']}")
        table.add_row(
            str(i + 1), icon, name_styled,
            Text(last_msg) if isinstance(last_msg, str) else last_msg,
            ts, unread,
            style=row_style,
        )
    return table


# ── Message rendering — fix #18 ───────────────────────────────────────────────

def render_messages(messages: list[Message], me_id: int, entity_name_str: str) -> None:
    """
    Render messages chronologically (oldest first, newest at bottom).
    Inserts day-group separators between date boundaries.  Fix #18.
    """
    console = get_console()
    p = get_palette()

    # messages arrives newest-first; reversed() gives oldest-first (correct chat order)
    ordered = list(reversed(messages))

    last_day: Optional[date_type] = None

    for msg in ordered:
        # Day separator (fix #18)
        if msg.date:
            local_date = msg.date.astimezone().date()
            if local_date != last_day:
                label = _day_label(msg.date)
                console.print(
                    Rule(f"[{p['dim']}]─── {label} ───[/]", style=p["separator"])
                )
                last_day = local_date

        _render_single_message(console, msg, me_id, p)


def _render_single_message(
    console: Console,
    msg: Message,
    me_id: int,
    p: dict,
) -> None:
    is_self  = msg.out or (msg.sender_id == me_id)
    ts       = format_ts(msg.date)
    msg_id   = f"[{p['dim']}]#{msg.id}[/]"

    if is_self:
        sender = Text("You", style=f"bold {p['self_msg']}")
    else:
        sender_name = "Unknown"
        if msg.sender:
            sender_name = entity_name(msg.sender)
        sender = Text(sender_name, style=f"bold {p['other_msg']}")

    content_parts: list[Text] = []
    if msg.text:
        content_parts.append(Text(msg.text))
    if msg.media:
        media_type = type(msg.media).__name__.replace("MessageMedia", "")
        # Try to get filename for documents
        label = media_type
        try:
            if hasattr(msg.media, "document"):
                for attr in msg.media.document.attributes:
                    fname = getattr(attr, "file_name", None)
                    if fname:
                        label = f"{media_type}: {fname}"
                        break
        except Exception:
            pass
        content_parts.append(Text(f"[{label}]", style=f"italic {p['dim']}"))
    if not content_parts:
        content_parts.append(Text("[empty]", style=p["dim"]))

    if msg.reply_to_msg_id:
        console.print(Text(f"  ╭─ replying to #{msg.reply_to_msg_id}", style=p["dim"]))

    reaction_str = ""
    if hasattr(msg, "reactions") and msg.reactions:
        try:
            parts = []
            for r in msg.reactions.results:
                emoji = getattr(r.reaction, "emoticon", "?")
                parts.append(f"{emoji}{r.count}")
            reaction_str = "  " + " ".join(parts)
        except Exception:
            pass

    edited = " [edited]" if msg.edit_date else ""

    header = Text()
    header.append("  ")
    header.append_text(sender)
    header.append(f"  {ts}  ", style=p["timestamp"])
    header.append(msg_id)
    header.append(edited, style=p["dim"])
    if reaction_str:
        header.append(reaction_str)

    console.print(header)
    for part in content_parts:
        console.print("  ", end="")
        console.print(part)
    console.print()


# ── Chat info panel ───────────────────────────────────────────────────────────

def render_chat_info(info: dict) -> Panel:
    p = get_palette()
    lines = []
    
    # Field display order for better UX
    field_order = ["name", "type", "username", "id", "members", "admins", 
                   "description", "pinned", "bot", "premium", "verified",
                   "broadcast", "megagroup", "phone", "restricted"]
    
    seen = set()
    
    # Display fields in preferred order
    for field in field_order:
        if field in info:
            v = info[field]
            if v is None or v == "":
                continue
            seen.add(field)
            
            # Format field labels nicely
            label = field.replace("_", " ").title()
            if field == "members":
                lines.append(f"[{p['dim']}]Members{'':<8}[/] [{p['accent']}]{v:,}[/]")
            elif field == "admins":
                lines.append(f"[{p['dim']}]Admins{'':<10}[/] [{p['accent']}]{v}[/]")
            elif field == "pinned" and v:
                lines.append(f"[{p['dim']}]Pinned Msg{'':<6}[/] [{p['accent']}]{v}[/]")
            elif field in ("bot", "premium", "verified", "broadcast", "megagroup", "restricted"):
                # Boolean fields - only show if True
                if v:
                    lines.append(f"[{p['accent']}]✓ {label}[/]")
            else:
                lines.append(f"[{p['dim']}]{label:<14}[/] [{p['fg']}]{v}[/]")
    
    # Display any remaining fields not in preferred order
    for k, v in info.items():
        if k in seen or v is None or v == "":
            continue
        label = k.replace("_", " ").title()
        lines.append(f"[{p['dim']}]{label:<14}[/] [{p['fg']}]{v}[/]")
    
    return Panel(
        "\n".join(lines),
        title=f"[{p['accent']}]Chat Info[/]",
        border_style=p["separator"],
        padding=(1, 2),
    )


# ── Banner ────────────────────────────────────────────────────────────────────

BANNER = r"""
  ████████╗ ██████╗      ██████╗██╗     ██╗
     ██╔══╝██╔════╝     ██╔════╝██║     ██║
     ██║   ██║  ███╗    ██║     ██║     ██║
     ██║   ██║   ██║    ██║     ██║     ██║
     ██║   ╚██████╔╝    ╚██████╗███████╗██║
     ╚═╝    ╚═════╝      ╚═════╝╚══════╝╚═╝
"""


def print_banner() -> None:
    from importlib.metadata import version as pkg_version, PackageNotFoundError
    try:
        ver = pkg_version("telegcli")
    except PackageNotFoundError:
        ver = "2.0.0-dev"

    console = get_console()
    p = get_palette()
    console.print(Text(BANNER, style=p["accent"]))
    console.print(Align.center(
        Text(f"Telegram CLI  •  MTProto  •  v{ver}", style=p["dim"])
    ))
    console.print()


# ── Status helpers ────────────────────────────────────────────────────────────

def print_success(msg: str) -> None:
    get_console().print(f"[tg.success]✓ {msg}[/]")

def print_error(msg: str) -> None:
    get_console().print(f"[tg.error]✗ {msg}[/]")

def print_warning(msg: str) -> None:
    get_console().print(f"[tg.warning]⚠ {msg}[/]")

def print_info(msg: str) -> None:
    get_console().print(f"[tg.accent]ℹ {msg}[/]")

def print_status(msg: str, style: str = "tg.dim") -> None:
    get_console().print(f"[{style}]{msg}[/]")
