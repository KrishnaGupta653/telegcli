"""
telegcli.commands.groups
────────────────────────
Smart chat grouping and tagging system.

Features:
  - Tag chats with custom labels
  - Filter chats by tags
  - Smart automatic grouping
"""

from __future__ import annotations

from rich.table import Table
from rich import box

from telegcli.core.config import get_config
from telegcli.ui.theme import get_console, get_palette, print_success, print_error, print_info, print_warning
from telegcli.utils.resolver import resolve_entity


async def cmd_tag(args: list[str]) -> None:
    """
    tag add <chat> <tags...>       → Add tags to a chat
    tag remove <chat> <tags...>    → Remove tags from a chat
    tag list [chat]                → List all tags (or tags for specific chat)
    tag show <tag>                 → Show all chats with a tag
    tag rename <old> <new>         → Rename a tag globally
    tag delete <tag>               → Delete a tag from all chats
    """
    cfg = get_config()
    console = get_console()
    p = get_palette()
    
    # Initialize tags structure if needed
    if "chat_tags" not in cfg:
        cfg.set("chat_tags", {})
    
    chat_tags = cfg.get("chat_tags", {})
    
    if not args:
        print_error("Usage: tag add|remove|list|show|rename|delete")
        return
    
    subcommand = args[0].lower()
    
    # ─── tag add <chat> <tags...> ───
    if subcommand == "add":
        if len(args) < 3:
            print_error("Usage: tag add <chat> <tags...>")
            return
        
        entity = await resolve_entity(args[1])
        if entity is None:
            return
        
        chat_id = str(entity.id)
        tags = [t.lower() for t in args[2:]]
        
        if chat_id not in chat_tags:
            chat_tags[chat_id] = []
        
        existing = set(chat_tags[chat_id])
        new_tags = [t for t in tags if t not in existing]
        
        if not new_tags:
            print_info(f"Chat already has tags: {', '.join(existing)}")
            return
        
        chat_tags[chat_id].extend(new_tags)
        cfg.set("chat_tags", chat_tags)
        print_success(f"Added tags to chat: {', '.join(new_tags)}")
    
    # ─── tag remove <chat> <tags...> ───
    elif subcommand == "remove":
        if len(args) < 3:
            print_error("Usage: tag remove <chat> <tags...>")
            return
        
        entity = await resolve_entity(args[1])
        if entity is None:
            return
        
        chat_id = str(entity.id)
        tags_to_remove = [t.lower() for t in args[2:]]
        
        if chat_id not in chat_tags:
            print_warning("Chat has no tags.")
            return
        
        original_count = len(chat_tags[chat_id])
        chat_tags[chat_id] = [t for t in chat_tags[chat_id] if t not in tags_to_remove]
        removed_count = original_count - len(chat_tags[chat_id])
        
        if removed_count == 0:
            print_info("No matching tags to remove.")
            return
        
        if not chat_tags[chat_id]:
            del chat_tags[chat_id]
        
        cfg.set("chat_tags", chat_tags)
        print_success(f"Removed {removed_count} tag(s).")
    
    # ─── tag list [chat] ───
    elif subcommand == "list":
        if len(args) > 1:
            # List tags for specific chat
            entity = await resolve_entity(args[1])
            if entity is None:
                return
            
            chat_id = str(entity.id)
            if chat_id not in chat_tags:
                print_info("Chat has no tags.")
                return
            
            tags = chat_tags[chat_id]
            table = Table(box=box.SIMPLE, header_style=f"bold {p['accent']}")
            table.add_column("Tags", style=p["success"])
            for tag in sorted(tags):
                table.add_row(tag)
            console.print(table)
        else:
            # List all tags with counts
            if not chat_tags:
                print_info("No tags yet. Use: tag add <chat> <tags...>")
                return
            
            tag_stats = {}
            for chat_id, tags in chat_tags.items():
                for tag in tags:
                    tag_stats[tag] = tag_stats.get(tag, 0) + 1
            
            table = Table(box=box.SIMPLE, header_style=f"bold {p['accent']}")
            table.add_column("Tag", style=p["success"])
            table.add_column("Chats", style=p["dim"], justify="right")
            
            for tag, count in sorted(tag_stats.items(), key=lambda x: -x[1]):
                table.add_row(tag, str(count))
            
            console.print(table)
    
    # ─── tag show <tag> ───
    elif subcommand == "show":
        if len(args) < 2:
            print_error("Usage: tag show <tag>")
            return
        
        tag_name = args[1].lower()
        matching_chats = []
        
        for chat_id, tags in chat_tags.items():
            if tag_name in tags:
                matching_chats.append(chat_id)
        
        if not matching_chats:
            print_warning(f"No chats with tag '{tag_name}'.")
            return
        
        table = Table(box=box.SIMPLE, header_style=f"bold {p['accent']}")
        table.add_column("Chat ID", style=p["dim"])
        table.add_column("Tags", style=p["success"])
        
        for chat_id in sorted(matching_chats):
            tags_str = ", ".join(sorted(chat_tags[chat_id]))
            table.add_row(chat_id, tags_str)
        
        console.print(table)
    
    # ─── tag rename <old> <new> ───
    elif subcommand == "rename":
        if len(args) < 3:
            print_error("Usage: tag rename <old_tag> <new_tag>")
            return
        
        old_tag = args[1].lower()
        new_tag = args[2].lower()
        
        count = 0
        for chat_id in chat_tags:
            if old_tag in chat_tags[chat_id]:
                chat_tags[chat_id].remove(old_tag)
                chat_tags[chat_id].append(new_tag)
                count += 1
        
        if count == 0:
            print_warning(f"Tag '{old_tag}' not found in any chat.")
            return
        
        cfg.set("chat_tags", chat_tags)
        print_success(f"Renamed '{old_tag}' → '{new_tag}' ({count} chat(s))")
    
    # ─── tag delete <tag> ───
    elif subcommand == "delete":
        if len(args) < 2:
            print_error("Usage: tag delete <tag>")
            return
        
        tag_to_delete = args[1].lower()
        count = 0
        
        for chat_id in list(chat_tags.keys()):
            if tag_to_delete in chat_tags[chat_id]:
                chat_tags[chat_id].remove(tag_to_delete)
                count += 1
                if not chat_tags[chat_id]:
                    del chat_tags[chat_id]
        
        if count == 0:
            print_warning(f"Tag '{tag_to_delete}' not found in any chat.")
            return
        
        cfg.set("chat_tags", chat_tags)
        print_success(f"Deleted tag '{tag_to_delete}' from {count} chat(s).")
    
    else:
        print_error(f"Unknown subcommand: {subcommand}")


async def cmd_group(args: list[str]) -> None:
    """
    group create <name> <tags...>   → Create named group with tags
    group list                       → List all groups
    group show <group>               → Show chats in group
    group delete <name>              → Delete a group
    """
    cfg = get_config()
    console = get_console()
    p = get_palette()
    
    # Initialize groups if needed
    if "chat_groups" not in cfg:
        cfg.set("chat_groups", {})
    
    groups = cfg.get("chat_groups", {})
    
    if not args:
        print_error("Usage: group create|list|show|delete")
        return
    
    subcommand = args[0].lower()
    
    # ─── group create <name> <tags...> ───
    if subcommand == "create":
        if len(args) < 3:
            print_error("Usage: group create <name> <tags...>")
            return
        
        group_name = args[1]
        group_tags = [t.lower() for t in args[2:]]
        
        if group_name in groups:
            print_warning(f"Group '{group_name}' already exists.")
            return
        
        groups[group_name] = group_tags
        cfg.set("chat_groups", groups)
        print_success(f"Created group '{group_name}' with tags: {', '.join(group_tags)}")
    
    # ─── group list ───
    elif subcommand == "list":
        if not groups:
            print_info("No groups created yet. Use: group create <name> <tags...>")
            return
        
        table = Table(box=box.SIMPLE, header_style=f"bold {p['accent']}")
        table.add_column("Group", style=p["success"])
        table.add_column("Tags", style=p["dim"])
        
        for name, tags in sorted(groups.items()):
            table.add_row(name, ", ".join(tags))
        
        console.print(table)
    
    # ─── group show <group> ───
    elif subcommand == "show":
        if len(args) < 2:
            print_error("Usage: group show <group_name>")
            return
        
        group_name = args[1]
        if group_name not in groups:
            print_error(f"Group '{group_name}' not found.")
            return
        
        required_tags = set(groups[group_name])
        chat_tags = cfg.get("chat_tags", {})
        matching_chats = []
        
        for chat_id, tags in chat_tags.items():
            chat_tag_set = set(tags)
            if required_tags.issubset(chat_tag_set):
                matching_chats.append((chat_id, tags))
        
        if not matching_chats:
            print_info(f"No chats found with tags: {', '.join(required_tags)}")
            return
        
        table = Table(box=box.SIMPLE, header_style=f"bold {p['accent']}")
        table.add_column("Chat ID", style=p["dim"])
        table.add_column("Tags", style=p["success"])
        
        for chat_id, tags in sorted(matching_chats):
            table.add_row(chat_id, ", ".join(sorted(tags)))
        
        console.print(table)
    
    # ─── group delete <name> ───
    elif subcommand == "delete":
        if len(args) < 2:
            print_error("Usage: group delete <group_name>")
            return
        
        group_name = args[1]
        if group_name not in groups:
            print_error(f"Group '{group_name}' not found.")
            return
        
        del groups[group_name]
        cfg.set("chat_groups", groups)
        print_success(f"Deleted group '{group_name}'.")
    
    else:
        print_error(f"Unknown subcommand: {subcommand}")
