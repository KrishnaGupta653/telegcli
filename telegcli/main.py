"""
telegcli — The most powerful Telegram terminal client.
Entry point with full CLI argument parsing.
"""

from __future__ import annotations

import sys
import asyncio

if sys.version_info < (3, 9):
    print("telegcli requires Python 3.9 or higher.")
    sys.exit(1)

import click
from importlib.metadata import version as pkg_version, PackageNotFoundError


def _get_version() -> str:
    try:
        return pkg_version("telegcli")
    except PackageNotFoundError:
        return "2.0.0-dev"


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(_get_version(), "-V", "--version", prog_name="telegcli")
@click.option(
    "--session", "-s",
    default=None,
    metavar="NAME",
    help="Named session to use (for multiple accounts). Default: 'telegcli'.",
    envvar="TELEGCLI_SESSION",
)
@click.option(
    "--config", "-c",
    default=None,
    metavar="PATH",
    help="Path to config directory. Default: ~/.config/telegcli.",
    envvar="TELEGCLI_CONFIG_DIR",
)
@click.option(
    "--log-level",
    default="WARNING",
    metavar="LEVEL",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"], case_sensitive=False),
    help="Logging verbosity. Default: WARNING.",
    envvar="TELEGCLI_LOG_LEVEL",
)
@click.option(
    "--no-color", is_flag=True, default=False,
    help="Disable all colour output.",
    envvar="NO_COLOR",
)
@click.option(
    "--proxy",
    default=None,
    metavar="SCHEME://HOST:PORT",
    help="Proxy (e.g. socks5://127.0.0.1:1080). Overrides config file.",
    envvar="TeleGCLI_PROXY",
)
def main(
    session: str | None,
    config: str | None,
    log_level: str,
    no_color: bool,
    proxy: str | None,
) -> None:
    """
    telegcli — Telegram CLI client.

    Read, send, search, stream, download, react, edit,
    manage contacts, schedule messages, and automate
    responses — all from your terminal.

    Quick start:
      telegcli                     Launch interactive REPL
      telegcli --session work      Use a named session (multi-account)
      telegcli --log-level DEBUG   Verbose mode for debugging
    """
    from telegcli.core.logging_setup import setup_logging
    from telegcli.core.config import init_config

    setup_logging(log_level)
    cfg = init_config(config_dir=config, session_name=session)

    if proxy:
        _apply_proxy_override(cfg, proxy)

    if no_color:
        cfg.set("no_color", True)

    from telegcli.app import TeleCli
    app = TeleCli(cfg)
    try:
        asyncio.run(app.run())
    except KeyboardInterrupt:
        _dim_print("\nBye.")
        sys.exit(0)


def _dim_print(msg: str) -> None:
    try:
        print(f"\033[90m{msg}\033[0m")
    except Exception:
        print(msg)


def _apply_proxy_override(cfg, raw: str) -> None:
    import re
    m = re.match(r"(socks5|socks4|http)://([^:]+):(\d+)", raw.lower())
    if m:
        cfg.set("proxy", {
            "scheme": m.group(1),
            "hostname": m.group(2),
            "port": int(m.group(3)),
        })
    else:
        click.echo(f"Warning: could not parse proxy '{raw}'. Ignoring.", err=True)


if __name__ == "__main__":
    main()
