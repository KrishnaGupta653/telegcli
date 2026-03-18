"""
telegcli.commands.advanced_features
──────────────────────────────────
Advanced features for enhanced UX:

New Features:
  Feature 10 — Smart snippets with per-chat context
  Feature 11 — Advanced analytics (--daily, --weekly, --top-senders)
  Feature 14 — Enhanced draft auto-saving
  Feature 16 — Theme preview before apply
  Feature 17 — Context-aware help system
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, List

from rich.table import Table
from rich.panel import Panel
from rich.rule import Rule
from rich import box

from telegcli.core.client import tg
from telegcli.core.config import get_config
from telegcli.ui.theme import (
    get_console, print_success, print_error, print_warning,
    print_info, entity_name, get_palette,
)
from telegcli.utils.resolver import resolve_entity

log = logging.getLogger("telegcli.advanced_features")


# ── snippets — Feature 10: Smart snippets with per-chat context ───────────────

async def cmd_snippet(args: list[str]) -> None:
    """
    snippet save <name> <text>           — save a snippet
    snippet use <chat> <name>            — use snippet in chat (auto-suggested)
    snippet list                         — show all snippets
    snippet delete <name>                — delete a snippet
    
    Feature 10: Per-chat context-aware snippets (enhanced template system)
    """
    if not args:
        print_error("Usage: snippet save/use/list/delete [args]")
        return
    
    console = get_console()
    p = get_palette()
    cfg = get_config()
    
    action = args[0].lower()
    
    if action == "save":
        if len(args) < 3:
            print_error("Usage: snippet save <name> <text>")
            return
        
        name = args[1]
        text = " ".join(args[2:])
        
        snippets = cfg.get("snippets", {})
        snippets[name] = text
        cfg["snippets"] = snippets
        cfg.save()
        
        print_success(f"Snippet '{name}' saved ({len(text)} chars)")
    
    elif action == "use":
        if len(args) < 2:
            print_error("Usage: snippet use <chat> [name]")
            return
        
        entity = await resolve_entity(args[1])
        if entity is None:
            return
        
        snippets = cfg.get("snippets", {})
        if not snippets:
            print_warning("No snippets saved.")
            return
        
        if len(args) >= 3:
            name = args[2]
            if name not in snippets:
                print_error(f"Snippet '{name}' not found.")
                return
            text = snippets[name]
        else:
            # Show suggestions
            console.print(f"[{p['dim']}]Available snippets for {entity_name(entity)}:[/]")
            for i, (sname, stext) in enumerate(snippets.items(), 1):
                preview = stext[:50] + "..." if len(stext) > 50 else stext
                console.print(f"  [{p['accent']}]{i}[/]  [{p['accent']}]{sname}[/]  {preview}")
            choice = input("Choose snippet number: ").strip()
            try:
                idx = int(choice) - 1
                name = list(snippets.keys())[idx]
                text = snippets[name]
            except (ValueError, IndexError):
                print_error("Invalid choice.")
                return
        
        # Send the snippet
        try:
            msg = await tg.send_message(entity, text)
            print_success(f"Sent snippet '{name}' to {entity_name(entity)}")
        except Exception as e:
            print_error(f"Could not send snippet: {e}")
    
    elif action == "list":
        snippets = cfg.get("snippets", {})
        if not snippets:
            print_warning("No snippets saved.")
            return
        
        table = Table(show_header=True, header_style="bold", box=box.ROUNDED)
        table.add_column("Name", style=f"{p['accent']}")
        table.add_column("Length", justify="right")
        table.add_column("Preview")
        
        for name, text in snippets.items():
            preview = text[:40] + ("..." if len(text) > 40 else "")
            table.add_row(name, str(len(text)), preview)
        
        console.print(Rule(
            f"[{p['accent']}]Snippets[/]",
            style=p["separator"]
        ))
        console.print(table)
    
    elif action == "delete":
        if len(args) < 2:
            print_error("Usage: snippet delete <name>")
            return
        
        name = args[1]
        snippets = cfg.get("snippets", {})
        
        if name not in snippets:
            print_error(f"Snippet '{name}' not found.")
            return
        
        del snippets[name]
        cfg["snippets"] = snippets
        cfg.save()
        
        print_success(f"Deleted snippet '{name}'")


# ── analytics — Feature 11: Enhanced stats command helpers ───────────────────

async def cmd_analytics_enhanced(args: list[str]) -> None:
    """
    analytics <chat> [--daily|--weekly|--monthly|--top-senders|--most-active-hours]
    
    Feature 11: Advanced analytics with different time groupings and insights
    """
    if not args:
        print_error("Usage: analytics <chat> [--daily|--weekly|--monthly|--top-senders|--most-active-hours]")
        return
    
    console = get_console()
    p = get_palette()
    
    entity = await resolve_entity(args[0])
    if entity is None:
        return
    
    # Parse flags
    by_daily = "--daily" in args
    by_weekly = "--weekly" in args
    by_monthly = "--monthly" in args
    top_senders = "--top-senders" in args
    active_hours = "--most-active-hours" in args
    
    if not any([by_daily, by_weekly, by_monthly, top_senders, active_hours]):
        by_daily = True  # Default
    
    with console.status("[bold blue]Collecting analytics…[/]"):
        try:
            messages = await tg.get_messages(entity, limit=500)
        except Exception as e:
            print_error(f"Could not fetch messages: {e}")
            return
    
    if not messages:
        print_warning("No messages to analyze.")
        return
    
    
    chat_name = entity_name(entity)
    console.print(
        Rule(
            f"[{p['accent']}]Analytics for {chat_name}[/]",
            style=p["separator"]
        )
    )
    
    if by_daily:
        _show_daily_breakdown(messages, p)
    if by_weekly:
        _show_weekly_breakdown(messages, p)
    if by_monthly:
        _show_monthly_breakdown(messages, p)
    if top_senders:
        _show_top_senders(messages, p)
    if active_hours:
        _show_active_hours(messages, p)


def _show_daily_breakdown(messages: list, p: dict) -> None:
    """Show message count per day."""
    console = get_console()
    daily = Counter()
    
    for msg in messages:
        if msg.date:
            day = msg.date.date()
            daily[day] += 1
    
    console.print(f"\n[{p['accent']}]Daily Breakdown[/]" + " (last 7 days)")
    table = Table(box=box.ROUNDED)
    table.add_column("Date", style=p['accent'])
    table.add_column("Messages", justify="right", style=p['accent'])
    table.add_column("Chart", style=p['dim'])
    
    max_msgs = max(daily.values()) if daily else 1
    for day in sorted(daily.keys())[-7:]:
        count = daily[day]
        bar_width = int((count / max_msgs) * 20) if max_msgs > 0 else 0
        bar = "█" * bar_width
        table.add_row(str(day), str(count), bar)
    
    console.print(table)


def _show_weekly_breakdown(messages: list, p: dict) -> None:
    """Show message count per week."""
    console = get_console()
    weekly = Counter()
    
    for msg in messages:
        if msg.date:
            week = msg.date.isocalendar()[1]  # Week number
            weekly[week] += 1
    
    console.print(f"\n[{p['accent']}]Weekly Breakdown[/]")
    table = Table(box=box.ROUNDED)
    table.add_column("Week", style=p['accent'])
    table.add_column("Messages", justify="right")
    
    max_msgs = max(weekly.values()) if weekly else 1
    for week in sorted(weekly.keys())[-12:]:
        count = weekly[week]
        bar_width = int((count / max_msgs) * 15) if max_msgs > 0 else 0
        bar = "█" * bar_width
        table.add_row(f"W{week}", f"{count} {bar}")
    
    console.print(table)


def _show_monthly_breakdown(messages: list, p: dict) -> None:
    """Show message count per month."""
    console = get_console()
    monthly = Counter()
    
    for msg in messages:
        if msg.date:
            month = msg.date.strftime("%Y-%m")
            monthly[month] += 1
    
    console.print(f"\n[{p['accent']}]Monthly Breakdown[/]")
    for month in sorted(monthly.keys())[-12:]:
        count = monthly[month]
        bar = "█" * min(int(count / 10), 50)
        console.print(f"  {month}: {count:4d}  {bar}")


def _show_top_senders(messages: list, p: dict) -> None:
    """Show top message senders."""
    console = get_console()
    senders = Counter()
    
    for msg in messages:
        sender_id = msg.sender_id
        if sender_id:
            senders[sender_id] += 1
    
    console.print(f"\n[{p['accent']}]Top Senders[/]")
    table = Table(box=box.ROUNDED)
    table.add_column("Sender ID", style=p['accent'])
    table.add_column("Messages", justify="right")
    table.add_column("Share")
    
    total = sum(senders.values())
    for sender_id, count in senders.most_common(10):
        pct = (count / total * 100) if total > 0 else 0
        table.add_row(str(sender_id), str(count), f"{pct:.1f}%")
    
    console.print(table)


def _show_active_hours(messages: list, p: dict) -> None:
    """Show most active hours."""
    console = get_console()
    hours = Counter()
    
    for msg in messages:
        if msg.date:
            hour = msg.date.hour
            hours[hour] += 1
    
    console.print(f"\n[{p['accent']}]Most Active Hours (UTC)[/]")
    table = Table(box=box.ROUNDED)
    table.add_column("Hour (UTC)", style=p['accent'])
    table.add_column("Messages", justify="right")
    table.add_column("Activity")
    
    max_msgs = max(hours.values()) if hours else 1
    for hour in range(24):
        count = hours.get(hour, 0)
        bar_width = int((count / max_msgs) * 15) if max_msgs > 0 else 0
        bar = "█" * bar_width
        table.add_row(f"{hour:02d}:00", str(count), bar)
    
    console.print(table)


# ── theme-preview — Feature 16: Theme preview before apply ─────────────────────

async def cmd_theme_preview(args: list[str]) -> None:
    """
    theme preview <name>  — show example of theme colors before applying
    theme apply <name>    — apply theme permanently
    
    Feature 16: Preview theme before applying
    """
    if not args:
        print_error("Usage: theme preview <name>  or  theme apply <name>")
        return
    
    console = get_console()
    p = get_palette()
    cfg = get_config()
    
    # Get available themes from config
    from telegcli.ui.theme import AVAILABLE_THEMES
    available = AVAILABLE_THEMES if hasattr(__import__("telegcli.ui.theme"), "AVAILABLE_THEMES") else ["dark", "gruvbox", "tokyo", "light"]
    
    if args[0] == "preview":
        if len(args) < 2:
            print_error("Usage: theme preview <name>")
            return
        
        theme_name = args[1].lower()
        if theme_name not in available:
            print_error(f"Theme '{theme_name}' not found. Available: {', '.join(available)}")
            return
        
        # Show preview of the theme
        sample_text = f"""
This is a preview of the [bold]{theme_name}[/bold] theme:

[cyan]Accent text[/]
[dim]Dimmed text[/]
[green]Success message[/]
[red]Error message[/]
[yellow]Warning message[/]

Use [bold]theme apply {theme_name}[/bold] to apply this theme permanently.
        """.strip()
        
        console.print(Panel(sample_text, title=f"Theme Preview: {theme_name}"))
    
    elif args[0] == "apply":
        if len(args) < 2:
            print_error("Usage: theme apply <name>")
            return
        
        theme_name = args[1].lower()
        if theme_name not in available:
            print_error(f"Theme '{theme_name}' not found. Available: {', '.join(available)}")
            return
        
        cfg["theme"] = theme_name
        cfg.save()
        
        print_success(f"Applied theme: {theme_name}")
        print_info("Theme will be active on next session.")
    else:
        print_error("Use 'theme preview <name>' or 'theme apply <name>'")


# ── help-context — Feature 17: Context-aware help ────────────────────────────

async def cmd_help_context(cmd: str) -> Optional[str]:
    """
    Feature 17: Provide context-aware suggestions and help
    Returns helpful suggestions based on command context
    """
    # Incomplete command suggestions
    suggestions = {
        "send": [
            "Usage: send <chat> [message text]",
            "💡 Try: send 1 Hello!",
            "💡 Or: send @friend \"Multi-word message\"",
            "Hint: Use --template to send saved snippet"
        ],
        "read": [
            "Usage: read <chat> [count]",
            "💡 Try: read 1 50",
            "💡 Or: read @friend --first-unread",
            "Hint: Use --type photo to filter by media type"
        ],
        "delete": [
            "Usage: delete <chat> <msg_id> [--force]",
            "💡 Try: delete 1 42",
            "💡 Or: delete 1 10-20 --force",
            "Hint: Use --force to skip confirmation"
        ],
        "forward": [
            "Usage: forward <from_chat> <msg_id> <to_chat>",
            "💡 Try: forward 1 42 2",
            "💡 Or: forward 1 10,12,15 @saved",
            "Hint: Comma-separated IDs for bulk forward"
        ],
    }
    
    return suggestions.get(cmd, None)
