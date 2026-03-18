"""
Webhook mode support for bot service.
Alternative to polling with HTTP callback handling via ngrok or custom webhook endpoint.
"""

import asyncio
import hashlib
import hmac
import json
import logging
from typing import Optional, Callable, Dict, Any
from dataclasses import dataclass
from datetime import datetime

try:
    from aiohttp import web
except ImportError:
    web = None


logger = logging.getLogger(__name__)


@dataclass
class WebhookConfig:
    """Configuration for webhook mode."""
    url: str  # External webhook URL for Telegram to POST to
    port: int = 5000  # Local HTTP server port
    host: str = "127.0.0.1"
    path: str = "/telegram"  # Webhook endpoint path
    secret_token: Optional[str] = None  # Optional secret for verification


class WebhookServer:
    """
    HTTP server for receiving Telegram bot updates via webhook.
    Provides alternative to polling for better resource usage.
    """

    def __init__(self, config: WebhookConfig, token: str):
        """
        Initialize webhook server.

        Args:
            config: WebhookConfig with URL and port
            token: Bot API token (for signature verification)
        """
        if web is None:
            raise ImportError(
                "aiohttp is required for webhook mode. Install with: pip install aiohttp"
            )

        self.config = config
        self.token = token
        self.app = web.Application()
        self.runner = None
        self.message_handler: Optional[Callable] = None
        self._setup_routes()

    def _setup_routes(self) -> None:
        """Setup HTTP routes for webhook."""
        self.app.router.add_post(self.config.path, self._handle_update)

    async def _handle_update(self, request: web.Request) -> web.Response:
        """
        Handle incoming webhook update from Telegram.

        Args:
            request: aiohttp request object

        Returns:
            HTTP 200 response
        """
        try:
            # Verify secret token if configured
            if self.config.secret_token:
                header_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
                if header_secret != self.config.secret_token:
                    logger.warning("Invalid secret token received")
                    return web.Response(status=403)

            # Parse update
            data = await request.json()
            logger.debug(f"Received webhook update: {data}")

            # Route to message handler
            if self.message_handler:
                message = data.get("message") or data.get("edited_message")
                if message:
                    await self.message_handler(message)

            return web.Response(status=200, text="OK")

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse webhook JSON: {e}", exc_info=True)
            return web.Response(status=400, text="Invalid JSON")
        except Exception as e:
            logger.error(f"Error handling webhook update: {e}", exc_info=True)
            return web.Response(status=500, text=f"Internal error: {str(e)}")

    async def start(self) -> None:
        """Start the webhook HTTP server."""
        if web is None:
            raise RuntimeError("aiohttp required for webhook mode")

        try:
            self.runner = web.AppRunner(self.app)
            await self.runner.setup()
            site = web.TCPSite(
                self.runner, self.config.host, self.config.port
            )
            await site.start()
            logger.info(
                f"Webhook server started on {self.config.host}:{self.config.port}"
            )
        except Exception as e:
            logger.error(f"Failed to start webhook server: {e}")
            raise

    async def stop(self) -> None:
        """Stop the webhook HTTP server."""
        if self.runner:
            await self.runner.cleanup()
            logger.info("Webhook server stopped")

    async def set_webhook(self, api_call_func: Callable) -> bool:
        """
        Register webhook with Telegram Bot API.

        Args:
            api_call_func: Async function to call Telegram API

        Returns:
            True if successful
        """
        try:
            result = await api_call_func(
                "setWebhook",
                {
                    "url": self.config.url,
                    "secret_token": self.config.secret_token,
                },
            )
            logger.info(f"Webhook registered: {result}")
            return True
        except Exception as e:
            logger.error(f"Failed to register webhook: {e}")
            return False

    async def delete_webhook(self, api_call_func: Callable) -> bool:
        """
        Delete webhook from Telegram Bot API.

        Args:
            api_call_func: Async function to call Telegram API

        Returns:
            True if successful
        """
        try:
            result = await api_call_func("deleteWebhook", {})
            logger.info(f"Webhook deleted: {result}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete webhook: {e}")
            return False

    async def get_webhook_info(self, api_call_func: Callable) -> Optional[Dict[str, Any]]:
        """
        Get current webhook information from Telegram.

        Args:
            api_call_func: Async function to call Telegram API

        Returns:
            Webhook info dict or None
        """
        try:
            result = await api_call_func("getWebhookInfo", {})
            return result
        except Exception as e:
            logger.error(f"Failed to get webhook info: {e}")
            return None


class NgrokTunnel:
    """
    Helper for creating ngrok tunnel to expose local webhook server.
    Automatically generates public URL for webhook registration.
    """

    def __init__(self, local_port: int = 5000):
        """
        Initialize ngrok tunnel helper.

        Args:
            local_port: Local port to tunnel
        """
        self.local_port = local_port
        self.tunnel_url: Optional[str] = None

    async def start(self) -> Optional[str]:
        """
        Start ngrok tunnel and return public URL.

        Returns:
            Public URL or None if failed
        """
        try:
            import pyngrok
            from pyngrok import ngrok as pyngrok_ngrok
        except ImportError:
            logger.error(
                "pyngrok is required for ngrok tunneling. "
                "Install with: pip install pyngrok"
            )
            return None

        try:
            # Start ngrok tunnel
            tunnel = pyngrok_ngrok.connect(self.local_port, "http")
            self.tunnel_url = tunnel.public_url
            logger.info(f"ngrok tunnel started: {self.tunnel_url}")
            return self.tunnel_url
        except Exception as e:
            logger.error(f"Failed to start ngrok tunnel: {e}")
            return None

    async def stop(self) -> None:
        """Stop ngrok tunnel."""
        try:
            from pyngrok import ngrok as pyngrok_ngrok
            pyngrok_ngrok.disconnect_all()
            logger.info("ngrok tunnel stopped")
        except Exception as e:
            logger.error(f"Failed to stop ngrok tunnel: {e}")

    @staticmethod
    async def generate_secret_token() -> str:
        """Generate a secure random secret token for webhook."""
        import secrets
        return secrets.token_urlsafe(32)
