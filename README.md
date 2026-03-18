# telegcli v2.0.0 — Telegram Terminal Client

The most powerful Telegram CLI client. Production-grade, MTProto-native,
fully async, and built for daily use.

---

## What's new in v2.0

| Area                   | Fix                                                                                                      |
| ---------------------- | -------------------------------------------------------------------------------------------------------- |
| **Rate limiting**      | All API calls auto-retry on FloodWait — no more crashes                                                  |
| **Structured logging** | Rotating logs at `~/.config/telegcli/logs/telegcli.log`                                                  |
| **Config validation**  | Pydantic-style coercion, schema migration, deep merge                                                    |
| **Security**           | Session + config files enforced at `chmod 600`                                                           |
| **Automations**        | Idempotent engine; `chat_filter`, `user_filter`, `max_fires_per_hour`, `only_private`; `automate remove` |
| **Export formats**     | JSON, CSV, TXT, HTML + `--all` for full history                                                          |
| **Clipboard**          | `copy <chat> <msg_id>` works via pyperclip                                                               |
| **Entity caching**     | Resolved entities cached client-side; no redundant network calls                                         |
| **CLI flags**          | `--version`, `--session`, `--config`, `--log-level`, `--no-color`, `--proxy`                             |
| **Modern packaging**   | `pyproject.toml` replaces legacy `setup.py`                                                              |
| **Async I/O**          | All `Prompt.ask`/`input()`/`getpass` replaced with async equivalents                                     |
| **Theme live-update**  | REPL prompt colour updates on next keystroke after `theme` change                                        |
| **Timezone**           | Stats hourly chart normalised to local timezone                                                          |
| **Day separators**     | Message view shows Today / Yesterday / date group headers                                                |
| **Tests**              | 40+ pytest tests covering config, rate limiter, automations, resolver, theme                             |

### New commands

| Command                                | Description                                     |
| -------------------------------------- | ----------------------------------------------- |
| `copy <chat> <msg_id>`                 | Copy message text to system clipboard           |
| `thread <chat> <msg_id>`               | Show a message and all its replies              |
| `gallery <chat> [n]`                   | List all media in a chat (type, name, size, ID) |
| `template save/use/list/delete`        | Save and reuse frequently sent messages         |
| `draft save/list/send/delete`          | Preserve unfinished messages across sessions    |
| `sessions list/switch/add`             | Manage multiple Telegram accounts               |
| `read --json`                          | Machine-readable message output (pipe to `jq`)  |
| `stats --json`                         | Machine-readable stats output                   |
| `export --format csv\|txt\|html\|json` | Multiple export formats                         |
| `export --all`                         | Export full chat history                        |
| `watch --out`                          | Include outgoing messages in watch stream       |
| `forward <chat> <id1,id2,...> <to>`    | Bulk forward multiple messages                  |

---

## Installation

```bash
# Clone and install
pip install -e .

# Or install dependencies directly
pip install -r requirements.txt
```

**Requirements:** Python 3.9+

Get API credentials at **https://my.telegram.org** → API development tools.

---

## Usage

```
telegcli [OPTIONS]

Options:
  -V, --version                Show version and exit
  -s, --session NAME           Named session for multi-account use
  -c, --config PATH            Custom config directory
  --log-level [DEBUG|INFO|WARNING|ERROR]
  --no-color                   Disable colour output
  --proxy SCHEME://HOST:PORT   Override proxy (e.g. socks5://127.0.0.1:1080)
  -h, --help                   Show this message and exit
```

### REPL commands

```
tg> list 50                     List 50 recent chats
tg> read 1                      Last 50 messages in chat #1
tg> read @friend 100            Last 100 from @friend
tg> read 3 search invoice       Search "invoice" in chat #3
tg> read @chat before 2024-06-01  Messages before a date
tg> read @chat --json | head    JSON output, pipe-friendly
tg> send 2 Hey, how are you?    Send inline
tg> send @chat --template greet Send a saved template
tg> reply 1 42 Thanks!          Reply to message #42
tg> edit 1 42 New text          Edit message #42
tg> delete 1 42                 Delete #42 everywhere
tg> forward 1 42,43 @saved      Bulk-forward to Saved Messages
tg> copy 1 42                   Copy #42 text to clipboard
tg> thread 1 42                 Show thread of #42
tg> preview 1 42                Show ASCII preview for image message #42
tg> react 1 42 👍               React to #42
tg> pin 1 42                    Pin #42
tg> watch                       Stream all incoming messages
tg> watch @friend               Stream only from @friend
tg> gallery 1                   List all media in chat #1
tg> upload 1 ~/file.pdf         Upload a file
tg> download 1 42               Download media from #42
tg> export @chat --format csv   Export as CSV
tg> export @chat --all          Export full history
tg> stats 1 1000 --json         Stats as JSON
tg> template save greet Hi!     Save a template
tg> template use greet          Preview template
tg> draft save @x Message here  Save a draft
tg> draft send 1                Send draft #1
tg> automate add busy I'm away --private --limit 5
tg> automate remove 1           Remove rule #1
tg> sessions list               Show all sessions
tg> sessions switch work        Instructions to switch
tg> bot add mybot <token>       Save bot token profile
tg> bot use mybot               Set active bot profile
tg> bot start                   Start Bot API polling service
tg> bot status                  Show bot health and runtime status
tg> bot logs 50                 Show recent bot service logs
tg> bot handlers                List loaded bot commands
tg> bot scaffold mybot          Create plugin scaffold
tg> schedule 1 2025-12-31 09:00 Happy new year!
tg> me                          Your account info
tg> theme gruvbox               Switch theme
tg> config msg_limit 100        Set a config value
tg> config image_preview false  Disable inline ASCII image previews
tg> config image_preview_width 64    Set preview width (16-120)
tg> config image_preview_max 5       Set max previews per read (0-10)
tg> config image_preview_photos_only true  Preview only photos, skip sticker docs
tg> help                        Full command list
```

When `image_preview` is enabled (default), `read` renders up to 3 inline
ASCII previews for image media in the fetched message window.

### Bot mode (token-based)

telegcli now supports a dedicated bot service mode in addition to user MTProto mode.

- User mode: existing account/session workflow (read/send/manage personal chats)
- Bot mode: Bot API token workflow with polling runner and plugin router

Quick start:

1. Create a bot with `@BotFather` and copy token
2. `bot add mybot <token>`
3. `bot use mybot`
4. `bot start`
5. Chat with your bot and use `/help`

Operational commands:

- `bot profiles` list saved bot profiles
- `bot status` show running state, last poll success, restarts, and last error
- `bot logs [n]` inspect recent service events
- `bot stop` stop polling service

Plugin system:

- `bot scaffold <profile>` creates `~/.config/telegcli/bots/<profile>/plugins/sample.py`
- Add Python files exporting `register(router)` to add bot commands dynamically
- Restart bot service after plugin changes

### Login methods

On first authorization, telegcli now lets you choose one of two login methods:

- `phone` (default): enter phone number and OTP code, with optional 2FA password
- `qr`: scan a terminal-rendered QR from Telegram mobile app

For QR login in Telegram mobile app:

1. Open Telegram on your phone
2. Go to `Settings -> Devices -> Link Desktop Device`
3. Scan the QR shown in telegcli

---

## Security

- Session file: `~/.config/telegcli/<session>.session` — `chmod 600` enforced
- Config file: `~/.config/telegcli/config.json` — `chmod 600` enforced
- Never share your session file — it grants full account access
- API hash is excluded from `config dump` output

---

## Multi-account usage

```bash
telegcli --session personal   # first account
telegcli --session work       # second account (separate session + history)
telegcli --session bot        # bot account
```

---

## Proxy

```bash
telegcli --proxy socks5://127.0.0.1:1080
```

Or in `config.json`:

```json
"proxy": {"scheme": "socks5", "hostname": "127.0.0.1", "port": 1080}
```

---

## Project structure

```
telegcli/
├── pyproject.toml
├── requirements.txt
├── tests/
│   ├── test_config.py
│   ├── test_rate_limiter.py
│   ├── test_automations.py
│   ├── test_resolver.py
│   ├── test_theme.py
│   ├── test_commands_misc.py
│   └── test_logging_setup.py
└── telegcli/
    ├── main.py                CLI entry point (click)
    ├── app.py                 App orchestrator
    ├── core/
    │   ├── client.py          Telethon wrapper (rate-limited)
    │   ├── config.py          Validated, versioned config
    │   ├── logging_setup.py   Structured rotating file logging
    │   └── rate_limiter.py    FloodWait auto-retry decorator
    ├── ui/
    │   ├── theme.py           Rich rendering, day separators
    │   ├── repl.py            Async REPL, live theme
    │   └── progress.py        Transfer progress bars
    ├── commands/
    │   ├── __init__.py        Dispatch table
    │   ├── messages.py        read/send/reply/edit/delete/forward/react/pin/copy/thread
    │   ├── chats.py           list/info/search/stats/export/gallery
    │   ├── files.py           upload/download
    │   ├── watch.py           Live streaming
    │   ├── contacts.py        contacts/add/block/unblock
    │   └── misc.py            me/schedule/automate/template/draft/sessions/theme/config
    └── utils/
        ├── resolver.py        Entity resolution with caching
        ├── editor.py          Async $EDITOR integration
        └── automations.py     Background auto-reply engine
```

---

## Running tests

```bash
pip install pytest pytest-asyncio pytest-mock
pytest tests/ -v
```

---

## Phase 2: Bot Management & Deployment (v2.1+)

### Full Bot Lifecycle Management (Like BotFather)

telegcli now provides complete bot creation and management capabilities directly from the CLI:

#### Interactive Bot Creation

```bash
tg> bot create
🤖 Bot Creation Wizard
Enter bot details:
Bot name: MyAwesomeBot
Bot username (without @): my_awesome_bot_42

📨 Sending to BotFather: creating bot 'MyAwesomeBot'...

✅ Bot created successfully!
Token: 1234567890:ABCdefGHIjklmNOPqrsTUVwxyzABCDEFGHI
Username: @my_awesome_bot_42

Save as bot profile? (y/n): y
Profile name (default 'my_awesome_bot_42'): mybot
✅ Profile 'mybot' saved!

Set as active profile? (y/n): y
✅ Active profile set to 'mybot'!
```

#### Bot Properties & Configuration

```bash
# View bot metadata (description, commands, privacy, webhook)
tg> bot properties mybot

# Edit bot properties interactively
tg> bot properties mybot
📋 Bot: mybot
👤 Token: 1234567890:...
📝 Description: (not set)
ℹ️  About: (not set)
🔒 Privacy: Enabled
⌚ Created: 2025-01-15 14:32:10
📌 Commands (5):
   /start - Start the bot
   /help - Get help
   /ping - Health check
   /settings - Configure bot
   /admin - Admin commands

Options: [d]escription | [a]bout | [c]ommands | [p]rivacy | [w]ebhook | [r]efresh | [x]done
Option: d
New description: A powerful Telegram bot built with telegcli
Description updated!
```

Set commands, privacy mode, webhook URL, admin rights — all without touching BotFather directly.

#### List All Your Bots

```bash
tg> bot profiles
Name              Mode        Active
mybot             polling     ✓
backup_bot        polling
utility_bot       webhook
```

#### Sync with BotFather

Fetch list of all bots managed by BotFather:

```bash
tg> bot sync
🔄 Syncing with BotFather...

Found 3 bots managed by BotFather

  • /mybot - @my_awesome_bot_42
  • /backup_bot - @backup_bot_v2
  • /utility_bot - @utility_bot_live
```

---

### Bot Health Checks (`bot doctor`)

Comprehensive diagnostics for bot configuration and connectivity:

```bash
tg> bot doctor mybot
🩺 Running health checks for 'mybot'...

Check                     Status     Message                          Time
Token Format              ✅ OK      Token format is valid           0ms
API Connectivity          ✅ OK      Successfully connected.         245ms
                                    Bot: @my_awesome_bot_42
Send Message Test         ℹ️  WARN   Test chat not configured        -

✅ All checks passed!
```

Validates:

- ✅ Token format (Telegram-official pattern)
- ✅ API connectivity (getMe call)
- ✅ Message sending ability
- ⚠️ Configuration issues
- ❌ Connection errors

---

### Webhook Mode (Alternative to Polling)

For scalable 24/7 bots, use webhook instead of polling:

#### Quick Setup

```bash
# Configure webhook for bot
tg> bot webhook mybot https://yourdomain.com:5000/telegram --secret secure-token-here

⚡ Webhook configured for 'mybot'!
URL: https://yourdomain.com:5000/telegram
Secret: secure-token-here...

# Start bot in webhook mode
tg> bot start --webhook
Bot service started in webhook mode on :5000
```

#### With ngrok (Tunneling)

For testing webhook locally without domain:

```bash
# Install: pip install pyngrok

# Auto-create ngrok tunnel
tg> bot webhook mybot --ngrok

🔗 ngrok tunnel started: https://abc123.ngrok.io/telegram
⚡ Webhook configured for 'mybot'!
```

#### Benefits

| Feature     | Polling  | Webhook      |
| ----------- | -------- | ------------ |
| Latency     | 25-30s   | <100ms       |
| CPU         | Constant | Event-driven |
| Scalability | Limited  | Unlimited    |
| Server Cost | Medium   | Low          |

---

### Hot Reload for Plugins

Edit plugins without restarting bot service:

```bash
# Terminal 1: Start bot
tg> bot start mybot
Bot service started (mybot).

# Terminal 2: Edit plugin
$ vi ~/.config/telegcli/bots/mybot/plugins/myfeature.py

# Changes automatically reload within 1 second
# Check logs with: tg> bot logs 5
[2025-01-15 14:35:22] plugin changed: myfeature.py — reloading
[2025-01-15 14:35:22] plugin reloaded: myfeature.py
```

Hot reload watches plugin directory continuously — no service interruption.

---

### Deploy Templates

telegcli includes production-ready templates for Railway, Render, systemd, and Docker.

#### Railway (One-Click Deploy)

```bash
# Copy railway.json to your repo root
cp deploy_templates/RAILWAY.md .

# Set env vars in Railway Dashboard:
# - BOT_PROFILE: my_bot
# - BOT_TOKEN: <your token>
# - BOT_MODE: polling (or webhook)

# Deploy
railway up
```

Auto-scaling, free tier, 24/7 uptime with hobby plan.

#### Render (Free + Self-Hosted)

```bash
# Use render.yaml for IaC deployment
cp deploy_templates/RENDER.md .

# Set environment:
# - BOT_PROFILE
# - BOT_TOKEN
# - BOT_MODE: polling or webhook

# Deploy from GitHub
# Render Dashboard > Create New > Web Service
# → Link repo → Select render.yaml → Deploy
```

Free tier: 750 hrs/month. Paid tier: 24/7 uptime.

#### VPS with systemd (Linode, DigitalOcean, Hetzner)

```bash
# 1. SSH into VPS
ssh user@vps.example.com

# 2. Install telegcli
pip install telegcli

# 3. Copy systemd service file
sudo cp deploy_templates/SYSTEMD.md /etc/systemd/system/telegcli-bot.service

# 4. Configure environment
sudo nano /etc/systemd/system/telegcli-bot.service
# Set BOT_PROFILE, BOT_MODE

# 5. Start service
sudo systemctl enable telegcli-bot
sudo systemctl start telegcli-bot

# 6. Monitor
sudo journalctl -u telegcli-bot -f
```

Full control, lowest cost, requires management.

#### Docker Compose (Any Server)

```bash
# Using docker-compose.yml from deploy_templates/

# Polling mode:
BOT_PROFILE=mybot docker-compose up -d

# Webhook mode with nginx:
BOT_PROFILE=mybot BOT_MODE=webhook docker-compose --profile webhook up -d

# View logs:
docker-compose logs -f telegcli-bot

# Run health check:
docker-compose exec telegcli-bot bot doctor mybot

# Stop:
docker-compose down
```

Portable, container-native, works anywhere Docker runs.

---

### Example Workflows

#### Development → Production Path

```bash
# 1. Create bot locally
tg> bot create
# → Creates mybot profile with token

# 2. Add local plugins
mkdir -p ~/.config/telegcli/bots/mybot/plugins
$ cat > handler.py
def register(router):
    async def status(ctx, args):
        await ctx.reply("🤖 Bot online!")
    router.command('status', status, 'Bot status check')

# 3. Test locally
tg> bot start mybot
tg> bot status
tg> bot logs 10

# 4. Deploy to production (Railway example)
cp deploy_templates/RAILWAY.md .
git add . && git commit -m "Add bot config"
git push
# → Railway auto-deploys in 90 seconds

# 5. Monitor remote bot
tg> bot status  # Always shows production bot's health
tg> bot doctor mybot  # Verify connectivity
tg> bot logs 50  # See production events
```

#### Multi-Bot Management

```bash
# Run multiple bots simultaneously
tg> bot add support_bot <token1>
tg> bot add notifier_bot <token2>
tg> bot add admin_bot <token3>

tg> bot use support_bot && bot start
# Support bot polling in background

tg> bot use notifier_bot && bot start
# Notifier bot polling in background (separate instance)

# Monitor all
tg> bot profiles
tg> bot status  # Shows currently active
```

Each bot has:

- Separate config + plugins
- Independent polling loop
- Own event log
- Unique profile name

---

### Full Command Reference (Bot Phase 2)

| Command                      | Description                                       |
| ---------------------------- | ------------------------------------------------- |
| `bot create`                 | Interactive wizard to create bot via BotFather    |
| `bot properties <name>`      | View/edit description, commands, privacy, webhook |
| `bot doctor <name> [--fix]`  | Run health checks (token, API, connectivity)      |
| `bot webhook <name> <url>`   | Configure webhook endpoint for bot                |
| `bot webhook <name> --ngrok` | Auto-create ngrok tunnel for testing              |
| `bot sync`                   | Fetch list of all bots from BotFather             |
| `bot profiles`               | List all saved bot profiles                       |
| `bot add <name> <token>`     | Save bot token profile (manual entry)             |
| `bot remove <name>`          | Delete bot profile                                |
| `bot use <name>`             | Set active bot profile                            |
| `bot start [name]`           | Start polling service (or webhook if configured)  |
| `bot stop`                   | Stop bot service                                  |
| `bot status`                 | Show runtime health, uptime, restart count        |
| `bot logs [n]`               | Show last n service events (default 40)           |
| `bot handlers`               | List loaded bot commands from plugins             |
| `bot send <chat_id> <text>`  | Manually send message via bot                     |
| `bot scaffold <name>`        | Create plugin scaffold directory                  |

---

## Contributing

Want to contribute? Great!

```bash
# Clone
git clone https://github.com/KrishnaGupta653/telegcli.git
cd telegcli

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dev dependencies
pip install -e ".[dev]"

# Make changes, test, commit
pytest tests/ -v
git add . && git commit -m "feat: describe change"
git push
```

### Areas for contribution

- [ ] Audio/video message rendering
- [ ] Scheduled message editor UI
- [ ] Performance profiling for large group chats
- [ ] Code generation for bot commands
- [ ] Telegram Stories support
- [ ] Custom theme creation guide

---

## License

MIT License. See LICENSE file.

---

## Support

- **Issues**: https://github.com/KrishnaGupta653/telegcli/issues
- **Documentation**: Check inline help: `tg> help <command>`
- **Examples**: See `tests/` and `deploy_templates/` directories
