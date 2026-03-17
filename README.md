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
tg> schedule 1 2025-12-31 09:00 Happy new year!
tg> me                          Your account info
tg> theme gruvbox               Switch theme
tg> config msg_limit 100        Set a config value
tg> help                        Full command list
```

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
