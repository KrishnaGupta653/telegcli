"""
telegcli.commands.contacts
────────────────────────
Commands: contacts, add, block, unblock
Fix #8: no blocking sync calls in async context
"""

from __future__ import annotations

from rich.table import Table
from rich import box

from telegcli.core.client import tg
from telegcli.ui.theme import (
    get_console, print_success, print_error, print_warning,
    entity_name, get_palette,
)
from telegcli.utils.resolver import resolve_entity


async def cmd_contacts(args: list[str]) -> None:
    """List all contacts."""
    console = get_console()
    p = get_palette()
    with console.status("[bold blue]Loading contacts…[/]"):
        contacts = await tg.get_contacts()
    if not contacts:
        print_warning("No contacts found.")
        return
    table = Table(
        show_header=True, header_style=f"bold {p['accent']}",
        box=box.SIMPLE, padding=(0, 1),
    )
    table.add_column("#",        style=p["dim"],    width=4)
    table.add_column("Name",     style=p["fg"],     ratio=2)
    table.add_column("Username", style=p["accent2"], ratio=1)
    table.add_column("Phone",    style=p["dim"],    ratio=1)
    table.add_column("Bot",      width=4)
    for i, user in enumerate(contacts):
        name     = entity_name(user)
        username = f"@{user.username}" if user.username else ""
        phone    = user.phone or ""
        bot      = "🤖" if getattr(user, "bot", False) else ""
        table.add_row(str(i + 1), name, username, phone, bot)
    console.print(table)
    console.print(f"[{p['dim']}]  {len(contacts)} contacts[/]")


async def cmd_add_contact(args: list[str]) -> None:
    """add <phone> <first_name> [last_name]"""
    if len(args) < 2:
        print_error("Usage: add <phone> <first_name> [last_name]")
        return
    phone      = args[0]
    first_name = args[1]
    last_name  = args[2] if len(args) > 2 else ""
    await tg.add_contact(phone, first_name, last_name)
    print_success(f"Added contact: {first_name} {last_name}  ({phone})")


async def cmd_block(args: list[str]) -> None:
    """block <user>"""
    if not args:
        print_error("Usage: block <user>")
        return
    entity = await resolve_entity(args[0])
    if entity is None:
        return
    await tg.block_user(entity)
    print_success(f"Blocked {entity_name(entity)}")


async def cmd_unblock(args: list[str]) -> None:
    """unblock <user>"""
    if not args:
        print_error("Usage: unblock <user>")
        return
    entity = await resolve_entity(args[0])
    if entity is None:
        return
    await tg.unblock_user(entity)
    print_success(f"Unblocked {entity_name(entity)}")
