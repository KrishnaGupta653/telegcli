"""Bot service commands for token-based bot mode."""

from __future__ import annotations

import asyncio
from datetime import datetime

from rich.panel import Panel
from rich.table import Table
from rich import box

from telegcli.bot.manager import get_bot_manager
from telegcli.bot.bot_registry import BotRegistry
from telegcli.bot.botfather import BotFatherClient
from telegcli.bot.doctor import BotDoctor
from telegcli.core.config import get_config
from telegcli.core.client import get_client
from telegcli.ui.theme import get_console, get_palette, print_error, print_info, print_success, print_warning


def _fmt_ts(ts: float | None) -> str:
    if not ts:
        return "-"
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


async def cmd_bot(args: list[str]) -> None:
    """
    bot profiles
    bot add <name> <token>
    bot remove <name>
    bot use <name>
    bot start [name]
    bot stop
    bot status
    bot logs [n]
    bot handlers
    bot send <chat_id> <text>
    bot scaffold <name>
    bot create
    bot modify <name>
    bot properties <name>
    bot doctor <name> [--fix]
    bot webhook <name> <url> [--secret]
    bot sync
    """
    mgr = get_bot_manager()
    cfg = get_config()
    console = get_console()
    p = get_palette()

    sub = (args[0].lower() if args else "status")

    # Show bot subcommands help
    if sub in ("help", "-h", "--help", "?"):
        help_text = """
[bold cyan]🤖 Bot Service Manager[/]

[bold yellow]What is Bot Mode?[/]
  Bot mode lets you run Telegram bots using Bot API tokens (from @BotFather).
  Unlike user mode (which uses your personal account), bots are automated accounts
  that can handle messages, reactions, and custom commands.

[bold yellow]Common Workflow:[/]
  1. bot create              ← Create NEW bot via BotFather (interactive)
  2. bot profiles            ← See saved bot tokens
  3. bot use <name>          ← Switch to a bot profile
  4. bot start               ← Start receiving messages
  5. bot status              ← Check if running
  6. bot logs                ← View recent activity

[bold yellow]Profile Management:[/]
  bot profiles               List all saved bot tokens
  bot add <name> <token>     Save a new bot token from @BotFather
  bot remove <name>          Delete a saved bot profile
  bot use <name>             Switch active bot profile

[bold yellow]Bot Operations:[/]
  bot start [name]           Turn on the bot (polling/webhook mode)
  bot stop                   Turn off the bot
  bot status                 Check if running + stats
  bot logs [n]               Show last n log entries
  bot handlers               List registered command handlers (/start, /help, etc)
  bot send <chat_id> <text>  Send message as bot (for testing)
  bot scaffold <name>        Create sample plugin for bot (for handlers/commands)

[bold yellow]Bot Configuration:[/]
  bot create                 Create NEW bot via BotFather (interactive wizard)
  bot properties <name>      View/edit bot description, commands, privacy
  bot doctor <name>          Health check (token valid? can send messages?)
  bot webhook <name> <url>   Setup webhook (real-time vs polling)
  bot sync                   Fetch all YOUR bots from BotFather
  bot test                   Test connection to BotFather

[bold yellow]Examples:[/]
  > bot create               Create new bot in BotFather
  > bot add mybot 123:ABCdef Save bot token
  > bot use mybot             Switch to it
  > bot start                 Turn it on
  > bot status                Check status
  > bot doctor mybot          Verify token works
  > bot handlers              See what /commands are loaded
  > bot scaffold mybot        Create sample plugin
  > bot properties mybot      Edit description/commands
  > bot webhook mybot https://example.com:443  Use webhook instead of polling
  > bot test                  Verify BotFather connection working

[bold yellow]Tips:[/]
  • Get bot token from @BotFather: /start → /newbot → name → username
  • Use 'bot scaffold' to create custom command plugins
  • Use 'bot doctor' to troubleshoot connection issues
  • Use 'bot test' to verify BotFather communication works
  • Webhook mode = instant updates (fast); Polling = every 25s (simple)
  • Visit https://core.telegram.org/bots for Bot API docs
"""
        console.print(help_text)
        return

    if sub == "profiles":
        profiles = mgr.list_profiles()
        if not profiles:
            print_info("No bot profiles. Add one with: bot add <name> <token>")
            return
        active = mgr.get_active_profile_name()
        table = Table(box=box.SIMPLE, header_style=f"bold {p['accent']}")
        table.add_column("Name", style=p["fg"])
        table.add_column("Mode", style=p["dim"])
        table.add_column("Active", width=8)
        for bp in profiles:
            table.add_row(bp.name, bp.mode, "✓" if bp.name == active else "")
        console.print(table)
        return

    if sub == "add":
        if len(args) < 3:
            print_error("Usage: bot add <name> <token>")
            return
        name, token = args[1], args[2]
        try:
            mgr.add_profile(name, token)
        except ValueError as e:
            print_error(str(e))
            return
        print_success(f"Bot profile '{name}' saved.")
        return

    if sub == "remove":
        if len(args) < 2:
            print_error("Usage: bot remove <name>")
            return
        if mgr.remove_profile(args[1]):
            print_success(f"Removed bot profile '{args[1]}'.")
        else:
            print_warning(f"Profile '{args[1]}' not found.")
        return

    if sub == "use":
        if len(args) < 2:
            print_error("Usage: bot use <name>")
            return
        try:
            mgr.use_profile(args[1])
            print_success(f"Active bot profile set to '{args[1]}'.")
        except ValueError as e:
            print_error(str(e))
        return

    if sub == "start":
        name = args[1] if len(args) > 1 else None
        try:
            svc = await mgr.start(name)
        except ValueError as e:
            print_error(str(e))
            return
        print_success(f"Bot service started ({svc.profile_name}).")
        return

    if sub == "stop":
        await mgr.stop()
        print_success("Bot service stopped.")
        return

    if sub == "status":
        st = mgr.status()
        lines = [
            f"[{p['dim']}]running:[/] {st.get('running')}",
            f"[{p['dim']}]profile:[/] {st.get('profile') or '-'}",
            f"[{p['dim']}]started_at:[/] {_fmt_ts(st.get('started_at'))}",
            f"[{p['dim']}]last_poll_ok:[/] {_fmt_ts(st.get('last_poll_ok_at'))}",
            f"[{p['dim']}]restart_count:[/] {st.get('restart_count')}",
            f"[{p['dim']}]last_error:[/] {st.get('last_error') or '-'}",
            f"[{p['dim']}]handlers:[/] {', '.join(st.get('loaded_commands', [])) or '-'}",
        ]
        console.print(Panel("\n".join(lines), title=f"[{p['accent']}]Bot Status[/]", border_style=p["separator"]))
        return

    if sub == "logs":
        n = 40
        if len(args) > 1 and args[1].lstrip("-").isdigit():
            n = int(args[1])
        svc = mgr.service()
        if not svc:
            print_warning("Bot service is not running.")
            return
        logs = svc.get_logs(n)
        if not logs:
            print_info("No logs yet.")
            return
        console.print(Panel("\n".join(logs), title=f"[{p['accent']}]Bot Logs[/]", border_style=p["separator"]))
        return

    if sub == "handlers":
        svc = mgr.service()
        if not svc:
            print_warning("Bot service is not running.")
            return
        rows = svc.router.list_commands()
        table = Table(box=box.SIMPLE, header_style=f"bold {p['accent']}")
        table.add_column("Command", style=p["accent"])
        table.add_column("Description", style=p["fg"])
        for name, help_text in rows:
            table.add_row(f"/{name}", help_text or "-")
        console.print(table)
        return

    if sub == "send":
        if len(args) < 3:
            print_error("Usage: bot send <chat_id> <text>")
            return
        svc = mgr.service()
        if not svc:
            print_warning("Bot service is not running.")
            return
        try:
            chat_id = int(args[1])
        except ValueError:
            print_error("chat_id must be an integer.")
            return
        text = " ".join(args[2:]).strip()
        if not text:
            print_error("Text cannot be empty.")
            return
        ok = await svc.send_text(chat_id, text)
        if ok:
            print_success("Message sent.")
        else:
            print_error("Message send failed. Check 'bot logs'.")
        return

    if sub == "scaffold":
        if len(args) < 2:
            print_error("Usage: bot scaffold <profile_name>")
            return
        profile_name = args[1]
        plugin_dir = cfg.config_dir / "bots" / profile_name / "plugins"
        plugin_dir.mkdir(parents=True, exist_ok=True)
        sample = plugin_dir / "sample.py"
        if not sample.exists():
            sample.write_text(
                "def register(router):\n"
                "    async def hello(ctx, args):\n"
                "        await ctx.reply('Hello from sample plugin')\n\n"
                "    router.command('hello', hello, 'Sample hello command')\n",
                encoding="utf-8",
            )
        print_success(f"Bot plugin scaffold ready at: {sample}")
        print_info("Start bot and run /hello in chat to test plugin.")
        return

    # ──────────────── Phase 2 Commands ───────────────────────────────────────

    if sub == "create":
        """Interactive bot creation via BotFather."""
        print_info("🤖 Bot Creation Wizard\n")
        print_info("This will guide you through creating a new bot with BotFather.")
        
        try:
            client = get_client()
            if not client.raw:
                print_error("User client not connected. Authenticate first with 'login'.")
                return
            
            # Prompt for bot details
            console.print("[dim]Enter bot details:[/]")
            bot_name = console.input("[accent]Bot name:[/] ").strip()
            if not bot_name:
                print_error("Bot name cannot be empty.")
                return
            
            bot_username = console.input("[accent]Bot username (without @):[/] ").strip()
            if not bot_username:
                print_error("Bot username cannot be empty.")
                return

            print_info(f"\n📨 Sending to BotFather: creating bot '{bot_name}'...\n")

            # Create BotFather client
            bf = BotFatherClient(client.raw)
            result = await bf.create_bot(bot_name, bot_username)

            if result.success:
                print_success(f"✅ Bot created successfully!")
                print_info(f"Token: {result.token}")
                print_info(f"Username: @{result.username}\n")

                # Ask to save profile
                save_choice = console.input("[accent]Save as bot profile? (y/n):[/] ").strip().lower()
                if save_choice in ("y", "yes"):
                    profile_name = console.input(f"[accent]Profile name (default '{result.username}'):[/] ").strip()
                    if not profile_name:
                        profile_name = result.username

                    try:
                        mgr.add_profile(profile_name, result.token)
                        print_success(f"✅ Profile '{profile_name}' saved!")
                        
                        # Ask to set as active
                        use_choice = console.input("[accent]Set as active profile? (y/n):[/] ").strip().lower()
                        if use_choice in ("y", "yes"):
                            mgr.use_profile(profile_name)
                            print_success(f"✅ Active profile set to '{profile_name}'!")
                    except ValueError as e:
                        print_error(f"Could not save profile: {e}")
            else:
                print_error(f"❌ Bot creation failed: {result.error}")
                if result.raw_response:
                    print_info(f"BotFather response: {result.raw_response}")

        except Exception as e:
            print_error(f"Error during bot creation: {e}")
        return

    if sub == "properties":
        """View or edit bot properties."""
        if len(args) < 2:
            print_error("Usage: bot properties <name>")
            return

        profile_name = args[1]
        registry = BotRegistry(cfg)
        
        try:
            profile = registry.get_bot_profile(profile_name)
            if not profile:
                print_error(f"Profile '{profile_name}' not found.")
                return

            info_str = registry.format_bot_info(profile_name)
            console.print(Panel(info_str, title=f"[{p['accent']}]Bot Properties[/]", border_style=p["separator"]))

            # Show options menu
            print_info("\nOptions: [d]escription | [a]bout | [c]ommands | [p]rivacy | [w]ebhook | [r]efresh | [x]done")
            choice = console.input("[accent]Option:[/] ").strip().lower()

            if choice == "d":
                description = console.input("[accent]New description:[/] ").strip()
                if description:
                    registry.set_bot_description(profile_name, description)
                    print_success("Description updated!")

            elif choice == "a":
                about = console.input("[accent]New about text:[/] ").strip()
                if about:
                    registry.set_bot_about_text(profile_name, about)
                    print_success("About text updated!")

            elif choice == "c":
                print_info("Enter commands in format: /cmd Description")
                print_info("(empty line to finish)")
                commands = []
                while True:
                    cmd_input = console.input("[accent]Command:[/] ").strip()
                    if not cmd_input:
                        break
                    parts = cmd_input.split(" ", 1)
                    if len(parts) == 2:
                        cmd_name = parts[0].lstrip("/")
                        cmd_desc = parts[1]
                        commands.append({"name": cmd_name, "description": cmd_desc})
                
                if commands:
                    registry.set_bot_commands(profile_name, commands)
                    print_success(f"Registered {len(commands)} commands!")

            elif choice == "p":
                privacy_choice = console.input("[accent]Enable privacy mode? (y/n):[/] ").strip().lower()
                privacy_enabled = privacy_choice in ("y", "yes")
                registry.set_bot_privacy(profile_name, privacy_enabled)
                print_success(f"Privacy mode {'enabled' if privacy_enabled else 'disabled'}!")

            elif choice == "w":
                webhook_url = console.input("[accent]Webhook URL:[/] ").strip()
                if webhook_url:
                    secret = console.input("[accent]Secret token (optional, press Enter to skip):[/] ").strip()
                    registry.set_webhook_config(profile_name, webhook_url, secret)
                    print_success("Webhook configured!")

        except Exception as e:
            print_error(f"Error: {e}")
        return

    if sub == "doctor":
        """Run bot health checks."""
        if len(args) < 2:
            print_error("Usage: bot doctor <name> [--fix]")
            return

        profile_name = args[1]
        registry = BotRegistry(cfg)
        profile = registry.get_bot_profile(profile_name)

        if not profile:
            print_error(f"Profile '{profile_name}' not found.")
            return

        token = profile.get("token")
        doctor = BotDoctor(token)

        print_info(f"🩺 Running health checks for '{profile_name}'...\n")

        # Run diagnosis
        results, passed = await doctor.run_full_diagnosis()

        # Display results
        result_table = doctor.format_results_table()
        table = Table(box=box.SIMPLE, header_style=f"bold {p['accent']}")
        table.add_column("Check", style=p["accent"])
        table.add_column("Status", style=p["fg"])
        table.add_column("Message", style=p["dim"])
        table.add_column("Time", style=p["dim"])

        for row in result_table:
            status_color = "green" if row["Status"] == "OK" else "yellow" if row["Status"] == "WARNING" else "red"
            table.add_row(row["Check"], f"[{status_color}]{row['Status']}[/]", row["Message"], row["Time"])

        console.print(table)

        if passed:
            print_success("✅ All checks passed!")
        else:
            print_warning("⚠️  Some checks failed. Review above for details.")
        return

    if sub == "webhook":
        """Configure webhook mode for bot."""
        if len(args) < 3:
            print_error("Usage: bot webhook <name> <url> [--secret <token>]")
            return

        profile_name = args[1]
        webhook_url = args[2]
        secret_token = ""

        # Parse optional --secret parameter
        if "--secret" in args:
            idx = args.index("--secret")
            if idx + 1 < len(args):
                secret_token = args[idx + 1]

        registry = BotRegistry(cfg)
        if registry.set_webhook_config(profile_name, webhook_url, secret_token):
            print_success(f"⚡ Webhook configured for '{profile_name}'!")
            print_info(f"URL: {webhook_url}")
            if secret_token:
                print_info(f"Secret: {secret_token[:10]}...")
        else:
            print_error(f"Profile '{profile_name}' not found.")
        return

    if sub == "sync":
        """Sync bot profiles with BotFather - auto-fetch and save all bots."""
        print_info("🔄 Syncing with BotFather...\n")
        print_info("(This may take 10-20 seconds as we click each bot to get tokens)\n")
        
        try:
            client = get_client()
            if not client.raw:
                print_error("User client not connected. Authenticate first with 'login'.")
                return

            bf = BotFatherClient(client.raw)
            print_info("📡 Fetching bot list from BotFather...")
            mybots_result = await bf.get_mybots_list()

            if mybots_result.get("success"):
                bots = mybots_result.get("bots", [])
                count = mybots_result.get("count", len(bots))
                print_success(f"\n✅ Found {count} bots from BotFather\n")
                
                saved_count = 0
                for bot_info in bots:
                    username = bot_info.get("username", "unknown")
                    token = bot_info.get("token", "")
                    name = bot_info.get("name", username)
                    
                    if token:
                        try:
                            # Auto-save bot profile
                            mgr.add_profile(username, token)
                            saved_count += 1
                            console.print(
                                f"  ✓ [{p['success']}]@{username}[/] "
                                f"([{p['dim']}]token: {token[:15]}...[/])"
                            )
                        except ValueError as e:
                            # Profile might already exist
                            console.print(
                                f"  ~ [{p['warning']}]@{username}[/] "
                                f"(already saved)"
                            )
                    else:
                        console.print(
                            f"  ✗ [{p['dim']}]@{username}[/] "
                            f"(could not extract token)"
                        )
                
                print_success(f"\n✅ Synced {saved_count}/{count} bots!")
                print_info(f"Use 'bot profiles' to see all saved bots")
                print_info(f"Use 'bot use @username' to switch to a bot")
            else:
                error = mybots_result.get('error', 'Unknown error')
                print_error(f"❌ Failed to sync: {error}")
                
                # Show debug info
                debug = mybots_result.get('debug', {})
                if debug:
                    console.print("\n[dim]Debug Information:[/]")
                    console.print(f"  Response has text: {debug.get('response_has_text', '?')}")
                    console.print(f"  Has buttons: {debug.get('has_buttons', False)}")
                    console.print(f"  Buttons found: {debug.get('buttons_found', 0)}")
                    console.print(f"  Tokens extracted: {debug.get('tokens_extracted', 0)}")
                    
                    attempts = debug.get('button_click_attempts', [])
                    if attempts:
                        console.print(f"\n[dim]Button Click Details ({len(attempts)} attempts):[/]")
                        for attempt in attempts:
                            status = "✓" if attempt.get('success') else "✗"
                            username = attempt.get('username', 'unknown')
                            token_status = "token✓" if attempt.get('token_found') else "token✗"
                            msgs = attempt.get('messages_checked', 0)
                            console.print(f"  [{status}] @{username} ({msgs} messages checked, {token_status})")
                            if attempt.get('error'):
                                console.print(f"      Error: {attempt['error']}")
                
                # Provide helpful troubleshooting
                if "did not respond" in error.lower():
                    print_warning("\nTroubleshooting:")
                    print_info("  1. Run 'bot test' to check BotFather connection")
                    print_info("  2. Make sure you're logged in: me")
                    print_info("  3. Check internet connection")
                    print_info("  4. Try again in a few seconds")
                elif "no bots" in error.lower() or debug.get('buttons_found', 0) == 0:
                    print_warning("\nYou don't have any bots yet. Create one:")
                    print_info("  1. Open Telegram and go to @BotFather")
                    print_info("  2. Send /newbot and follow the prompts")
                    print_info("  3. Copy the token")
                    print_info("  4. Use: bot add <name> <token>")

        except Exception as e:
            print_error(f"Error during sync: {e}")
            print_warning("If this persists, try manually adding bots: bot add <name> <token>")
        return

    if sub == "test":
        """Test BotFather connection."""
        print_info("🧪 Testing BotFather connection...\n")
        
        try:
            client = get_client()
            if not client.raw:
                print_error("User client not connected. Authenticate first with 'login'.")
                return

            bf = BotFatherClient(client.raw)
            result = await bf.test_connection()
            
            if result.get("success"):
                print_success(f"✅ {result.get('message')}")
                if result.get('response_preview'):
                    print_info(f"Response: {result.get('response_preview')}")
            else:
                print_error(f"❌ {result.get('message')}")
                
                # Debug: show what we got
                if result.get('debug_info'):
                    print_warning("\nDebug info:")
                    print_info(f"  Messages fetched: {result.get('debug_info', {}).get('messages_count', 0)}")
                    if result.get('debug_info', {}).get('latest_messages'):
                        for i, msg_info in enumerate(result.get('debug_info', {}).get('latest_messages', [])[:3]):
                            print_info(f"    [{i}] From: {msg_info.get('from')}, ID: {msg_info.get('id')}, Text: {msg_info.get('text', '(media/buttons)')[:50]}")
                
                if result.get('tips'):
                    print_warning("\nTroubleshooting tips:")
                    for tip in result.get('tips', []):
                        print_info(f"  • {tip}")
                
                if result.get('error'):
                    print_info(f"\nTechnical error: {result.get('error')}")
        
        except Exception as e:
            print_error(f"Error testing connection: {e}")
        return

    if sub == "sync":
        print_info("🔄 Syncing with BotFather...\n")
        print_info("(This may take 10-20 seconds as we click each bot to get tokens)\n")
        
        try:
            client = get_client()
            if not client.raw:
                print_error("User client not connected. Authenticate first with 'login'.")
                return

            bf = BotFatherClient(client.raw)
            print_info("📡 Fetching bot list from BotFather...")
            mybots_result = await bf.get_mybots_list()

            if mybots_result.get("success"):
                bots = mybots_result.get("bots", [])
                count = mybots_result.get("count", len(bots))
                print_success(f"\n✅ Found {count} bots from BotFather\n")
                
                saved_count = 0
                for bot_info in bots:
                    username = bot_info.get("username", "unknown")
                    token = bot_info.get("token", "")
                    name = bot_info.get("name", username)
                    
                    if token:
                        try:
                            # Auto-save bot profile
                            mgr.add_profile(username, token)
                            saved_count += 1
                            console.print(
                                f"  ✓ [{p['success']}]@{username}[/] "
                                f"([{p['dim']}]token: {token[:15]}...[/])"
                            )
                        except ValueError as e:
                            # Profile might already exist
                            console.print(
                                f"  ~ [{p['warning']}]@{username}[/] "
                                f"(already saved)"
                            )
                    else:
                        console.print(
                            f"  ✗ [{p['dim']}]@{username}[/] "
                            f"(could not extract token)"
                        )
                
                print_success(f"\n✅ Synced {saved_count}/{count} bots!")
                print_info(f"Use 'bot profiles' to see all saved bots")
                print_info(f"Use 'bot use @username' to switch to a bot")
            else:
                error = mybots_result.get('error', 'Unknown error')
                print_error(f"❌ Failed to sync: {error}")
                
                # Show detailed debug info
                debug_info = mybots_result.get('debug', {})
                if debug_info:
                    print_warning("\n🐛 Debug Information:")
                    print_info(f"  Response has text: {debug_info.get('response_has_text', False)}")
                    print_info(f"  Has buttons: {debug_info.get('has_buttons', False)}")
                    print_info(f"  Buttons found: {debug_info.get('buttons_found', 0)}")
                    print_info(f"  Tokens extracted: {debug_info.get('tokens_extracted', 0)}")
                    
                    # Show details of step-by-step workflow for each bot
                    attempts = debug_info.get('username_extraction_attempts', [])
                    if attempts:
                        print_warning("\n  Token extraction workflow:")
                        for attempt in attempts:
                            username = attempt.get('username', 'unknown')
                            success = attempt.get('success', False)
                            status_icon = "✓" if success else "✗"
                            print_info(f"    {status_icon} @{username}")
                            
                            # Show step-by-step details
                            for step in attempt.get('steps', []):
                                action = step.get('action', 'unknown')
                                step_success = step.get('success', False)
                                step_icon = "  ✓" if step_success else "  ✗"
                                
                                if action == "init_token_request":
                                    print_info(f"       {step_icon} Request token: {step.get('command')}")
                                    if step.get('response_preview'):
                                        print_info(f"           BotFather: {step.get('response_preview')[:60]}...")
                                elif action == "select_bot_for_token":
                                    token_found = step.get('token_found', False)
                                    token_icon = "🔑" if token_found else "✗"
                                    print_info(f"       {step_icon} Select bot: {step.get('command')} {token_icon}")
                                    if step.get('response_preview'):
                                        print_info(f"           BotFather: {step.get('response_preview')[:60]}...")
                                elif action == "exception":
                                    error = step.get('error', 'unknown')
                                    print_info(f"       ✗ Exception: {error[:60]}")
                            
                            if attempt.get('error'):
                                print_info(f"       Error: {attempt.get('error')[:60]}")
                
                # Provide helpful troubleshooting
                if "did not respond" in error.lower():
                    print_warning("\nTroubleshooting:")
                    print_info("  1. Make sure you're logged in: me")
                    print_info("  2. Check internet connection")
                    print_info("  3. Try again in a few seconds")
                elif "no bots" in error.lower():
                    print_warning("\nYou don't have any bots yet. Create one:")
                    print_info("  1. Open Telegram and go to @BotFather")
                    print_info("  2. Send /newbot and follow the prompts")
                    print_info("  3. Copy the token")
                    print_info("  4. Use: bot add <name> <token>")

        except Exception as e:
            print_error(f"Error during sync: {e}")
            print_warning("If this persists, try manually adding bots: bot add <name> <token>")
        return

    print_error(
        "Unknown bot subcommand. Try: bot help"
    )
