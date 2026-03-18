"""
telegcli.commands.backup
────────────────────────
Backup, restore, and data export capabilities

Features:
  - Full message export with tar.gz compression
  - Selective backup by chat or date range
  - Restore functionality for migration
  - JSON/CSV export for analysis
"""

from __future__ import annotations

import asyncio
import gzip
import json
import tarfile
import datetime
from pathlib import Path
from typing import Optional

from rich.progress import Progress
from rich.table import Table
from rich import box

from telegcli.core.client import tg
from telegcli.core.config import get_config
from telegcli.ui.theme import (
    get_console, get_palette, entity_name, format_ts,
    print_success, print_error, print_info, print_warning
)
from telegcli.utils.resolver import resolve_entity


async def cmd_backup(args: list[str]) -> None:
    """
    backup <path> [--chat <chat>] [--since <date>] [--until <date>] [--format tar|json|csv]
      → Backup messages to file
    
    Examples:
      backup ~/backup.tar.gz              # Full backup
      backup ~/backup.json --format json  # JSON export
      backup ~/work.tar.gz --chat @work   # Backup single chat
      backup ~/jan.tar.gz --since 2025-01-01 --until 2025-01-31
    """
    cfg = get_config()
    console = get_console()
    p = get_palette()
    
    if not args:
        print_error("Usage: backup <path> [--chat <chat>] [--since <date>] [--until <date>] [--format tar|json|csv]")
        return
    
    backup_path = Path(args[0]).expanduser()
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Parse arguments
    chat_filter = None
    since_date = None
    until_date = None
    backup_format = "tar"  # default
    
    i = 1
    while i < len(args):
        if args[i] == "--chat" and i + 1 < len(args):
            entity = await resolve_entity(args[i + 1])
            if entity:
                chat_filter = entity
            i += 2
        elif args[i] == "--since" and i + 1 < len(args):
            try:
                since_date = datetime.datetime.strptime(args[i + 1], "%Y-%m-%d")
            except ValueError:
                print_error("Date format must be YYYY-MM-DD")
                return
            i += 2
        elif args[i] == "--until" and i + 1 < len(args):
            try:
                until_date = datetime.datetime.strptime(args[i + 1], "%Y-%m-%d")
            except ValueError:
                print_error("Date format must be YYYY-MM-DD")
                return
            i += 2
        elif args[i] == "--format" and i + 1 < len(args):
            backup_format = args[i + 1].lower()
            i += 2
        else:
            i += 1
    
    console.print(f"[{p['info']}]Starting backup…[/]")
    
    # Collect dialogs to backup
    if chat_filter:
        dialogs = [await tg.get_entity(chat_filter)]
    else:
        dialogs = await tg.get_dialogs()
    
    backup_data = []
    
    with Progress() as progress:
        task = progress.add_task("[cyan]Exporting messages...", total=len(dialogs))
        
        for dialog in dialogs:
            messages = []
            try:
                async for msg in tg.iter_messages(dialog, limit=None):
                    # Apply date filters
                    if since_date and msg.date < since_date:
                        continue
                    if until_date and msg.date > until_date:
                        continue
                    
                    msg_data = {
                        "id": msg.id,
                        "date": msg.date.isoformat() if msg.date else None,
                        "sender": entity_name(msg.sender) if msg.sender else "Unknown",
                        "text": msg.text or "",
                        "media_type": type(msg.media).__name__ if msg.media else None,
                    }
                    messages.append(msg_data)
            except Exception as e:
                print_warning(f"Could not export from chat: {str(e)}")
                progress.update(task, advance=1)
                continue
            
            if messages:
                backup_data.append({
                    "chat": entity_name(dialog),
                    "chat_id": dialog.id,
                    "message_count": len(messages),
                    "messages": messages
                })
            
            progress.update(task, advance=1)
    
    # Write backup file
    if backup_format == "json":
        with open(backup_path, "w") as f:
            json.dump(backup_data, f, indent=2, default=str)
        print_success(f"Backup saved: {backup_path}")
        print_info(f"Format: JSON | Chats: {len(backup_data)} | Total messages: {sum(c['message_count'] for c in backup_data)}")
    
    elif backup_format == "csv":
        import csv
        with open(backup_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Chat", "Message ID", "Date", "Sender", "Text"])
            for chat_data in backup_data:
                for msg in chat_data["messages"]:
                    writer.writerow([
                        chat_data["chat"],
                        msg["id"],
                        msg["date"],
                        msg["sender"],
                        msg["text"][:100]  # Truncate long messages
                    ])
        print_success(f"Backup saved: {backup_path}")
        print_info(f"Format: CSV | Chats: {len(backup_data)}")
    
    else:  # tar.gz format
        with tarfile.open(backup_path, "w:gz") as tar:
            # Create JSON temp file
            json_data = json.dumps(backup_data, indent=2, default=str)
            tar.addfile(
                tarfile.TarInfo(name="backup.json"),
                fileobj=__import__("io").BytesIO(json_data.encode())
            )
        print_success(f"Backup saved: {backup_path}")
        print_info(f"Format: TAR.GZ | Chats: {len(backup_data)} | Compressed size: {backup_path.stat().st_size / (1024*1024):.2f} MB")


async def cmd_restore(args: list[str]) -> None:
    """
    restore <path> [--chat <target_chat>] [--preview]
      → Restore messages from backup
      
    Examples:
      restore ~/backup.tar.gz --preview       # Show what would restore
      restore ~/backup.tar.gz --chat 1        # Restore to chat #1
    """
    console = get_console()
    p = get_palette()
    
    if not args:
        print_error("Usage: restore <path> [--chat <target_chat>] [--preview]")
        return
    
    backup_path = Path(args[0]).expanduser()
    
    if not backup_path.exists():
        print_error(f"Backup file not found: {backup_path}")
        return
    
    target_chat = None
    preview_mode = "--preview" in args
    
    # Parse target chat
    for i, arg in enumerate(args):
        if arg == "--chat" and i + 1 < len(args):
            entity = await resolve_entity(args[i + 1])
            if entity:
                target_chat = entity
            break
    
    # Read backup file
    try:
        if str(backup_path).endswith(".tar.gz"):
            with tarfile.open(backup_path, "r:gz") as tar:
                member = tar.extractfile("backup.json")
                backup_data = json.load(member)
        elif str(backup_path).endswith(".json"):
            with open(backup_path) as f:
                backup_data = json.load(f)
        else:
            print_error("Unsupported backup format. Use .tar.gz or .json")
            return
    except Exception as e:
        print_error(f"Could not read backup: {str(e)}")
        return
    
    if preview_mode:
        # Show what would be restored
        table = Table(box=box.SIMPLE, header_style=f"bold {p['accent']}")
        table.add_column("Chat", style=p["success"])
        table.add_column("Messages", style=p["dim"], justify="right")
        
        for chat_data in backup_data:
            table.add_row(chat_data["chat"], str(chat_data["message_count"]))
        
        console.print(table)
        print_info(f"Total: {len(backup_data)} chats, {sum(c['message_count'] for c in backup_data)} messages")
        return
    
    if not target_chat:
        print_error("Restore requires target chat: --chat <target_chat>")
        return
    
    print_warning("Restore would re-send messages. This is not a true restore, just reference.")
    print_info("Use --preview to see what would happen first.")


async def cmd_export(args: list[str]) -> None:
    """
    export <chat> <path> [--format json|csv] [--limit <n>]
      → Export messages from specific chat
    
    Examples:
      export @team ~/team_chat.json                  # JSON export
      export 1 ~/messages.csv --format csv --limit 1000  # CSV with limit
    """
    console = get_console()
    p = get_palette()
    
    if len(args) < 2:
        print_error("Usage: export <chat> <path> [--format json|csv] [--limit <n>]")
        return
    
    entity = await resolve_entity(args[0])
    if entity is None:
        return
    
    export_path = Path(args[1]).expanduser()
    export_format = "json"
    limit = None
    
    # Parse options
    for i, arg in enumerate(args[2:], start=2):
        if arg == "--format" and i + 1 < len(args):
            export_format = args[i + 1].lower()
        elif arg == "--limit" and i + 1 < len(args):
            try:
                limit = int(args[i + 1])
            except ValueError:
                pass
    
    messages = []
    
    with console.status(f"[cyan]Exporting from {entity_name(entity)}…[/]"):
        async for msg in tg.iter_messages(entity, limit=limit):
            messages.append({
                "id": msg.id,
                "date": msg.date.isoformat() if msg.date else None,
                "sender": entity_name(msg.sender) if msg.sender else "Unknown",
                "text": msg.text or "",
                "media_type": type(msg.media).__name__ if msg.media else None,
            })
    
    if export_format == "csv":
        import csv
        with open(export_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Message ID", "Date", "Sender", "Text", "Media Type"])
            for msg in messages:
                writer.writerow([msg["id"], msg["date"], msg["sender"], msg["text"][:100], msg["media_type"] or ""])
    else:
        with open(export_path, "w") as f:
            json.dump(messages, f, indent=2, default=str)
    
    print_success(f"Exported {len(messages)} messages to {export_path}")
