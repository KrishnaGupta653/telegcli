"""
Bot health checks and diagnostics.
Doctor command for validating bot configuration and connectivity.
"""

import asyncio
import time
import logging
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass


logger = logging.getLogger(__name__)


@dataclass
class HealthCheckResult:
    """Result of a single health check."""
    name: str
    status: str  # "ok" | "warning" | "error"
    message: str
    timestamp: float = 0
    duration_ms: float = 0

    def __post_init__(self):
        if self.timestamp == 0:
            self.timestamp = time.time()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "message": self.message,
            "duration_ms": self.duration_ms,
        }


class BotDoctor:
    """
    Diagnostic utility for validating bot configuration and health.
    Performs token validation, API connectivity, and configuration checks.
    """

    def __init__(self, bot_token: str, api_call_func=None):
        """
        Initialize bot doctor.

        Args:
            bot_token: Bot API token
            api_call_func: Async function for making API calls (optional)
        """
        self.bot_token = bot_token
        self.api_call_func = api_call_func
        self.results: list[HealthCheckResult] = []

    def _validate_token_format(self) -> bool:
        """Validate bot token format."""
        import re
        pattern = r"^\d+:[A-Za-z0-9_-]{20,}$"
        return bool(re.match(pattern, self.bot_token))

    async def check_token_format(self) -> HealthCheckResult:
        """Check token format validity."""
        start = time.time()
        is_valid = self._validate_token_format()
        duration_ms = (time.time() - start) * 1000

        if is_valid:
            return HealthCheckResult(
                name="Token Format",
                status="ok",
                message="Token format is valid",
                duration_ms=duration_ms,
            )
        else:
            return HealthCheckResult(
                name="Token Format",
                status="error",
                message="Invalid token format. Expected: <bot_id>:<api_token>",
                duration_ms=duration_ms,
            )

    async def check_api_connectivity(self) -> HealthCheckResult:
        """Check connectivity to Telegram Bot API."""
        if not self.api_call_func:
            return HealthCheckResult(
                name="API Connectivity",
                status="warning",
                message="API call function not configured (skipped)",
            )

        start = time.time()
        try:
            result = await asyncio.wait_for(
                self.api_call_func("getMe", {}), timeout=10
            )
            duration_ms = (time.time() - start) * 1000

            if result and result.get("ok"):
                bot_name = result.get("result", {}).get("username", "unknown")
                return HealthCheckResult(
                    name="API Connectivity",
                    status="ok",
                    message=f"Successfully connected. Bot: @{bot_name}",
                    duration_ms=duration_ms,
                )
            else:
                error = result.get("description", "Unknown error")
                return HealthCheckResult(
                    name="API Connectivity",
                    status="error",
                    message=f"API error: {error}",
                    duration_ms=duration_ms,
                )

        except asyncio.TimeoutError:
            duration_ms = (time.time() - start) * 1000
            return HealthCheckResult(
                name="API Connectivity",
                status="error",
                message="Timeout connecting to Bot API (>10s)",
                duration_ms=duration_ms,
            )
        except Exception as e:
            duration_ms = (time.time() - start) * 1000
            return HealthCheckResult(
                name="API Connectivity",
                status="error",
                message=f"Connection failed: {str(e)}",
                duration_ms=duration_ms,
            )

    async def check_sendmessage(self, test_chat_id: int = -1001234567890) -> HealthCheckResult:
        """
        Test sending a message to a test chat.

        Args:
            test_chat_id: Chat ID for test message (default is dummy)

        Returns:
            Health check result
        """
        if not self.api_call_func or test_chat_id == -1001234567890:
            return HealthCheckResult(
                name="Send Message Test",
                status="warning",
                message="Test chat not configured (skipped)",
            )

        start = time.time()
        try:
            result = await asyncio.wait_for(
                self.api_call_func(
                    "sendMessage",
                    {
                        "chat_id": test_chat_id,
                        "text": "🤖 Bot health check — all systems operational",
                    },
                ),
                timeout=10,
            )
            duration_ms = (time.time() - start) * 1000

            if result and result.get("ok"):
                return HealthCheckResult(
                    name="Send Message Test",
                    status="ok",
                    message=f"Successfully sent test message to chat {test_chat_id}",
                    duration_ms=duration_ms,
                )
            else:
                error = result.get("description", "Unknown error")
                return HealthCheckResult(
                    name="Send Message Test",
                    status="error",
                    message=f"Send failed: {error}",
                    duration_ms=duration_ms,
                )

        except asyncio.TimeoutError:
            duration_ms = (time.time() - start) * 1000
            return HealthCheckResult(
                name="Send Message Test",
                status="error",
                message="Send message timeout (>10s)",
                duration_ms=duration_ms,
            )
        except Exception as e:
            duration_ms = (time.time() - start) * 1000
            return HealthCheckResult(
                name="Send Message Test",
                status="error",
                message=f"Send failed: {str(e)}",
                duration_ms=duration_ms,
            )

    async def check_getme(self) -> Optional[Dict[str, Any]]:
        """
        Get bot information from API.

        Returns:
            Bot info dict or None
        """
        if not self.api_call_func:
            return None

        try:
            result = await asyncio.wait_for(
                self.api_call_func("getMe", {}), timeout=10
            )
            if result and result.get("ok"):
                return result.get("result")
        except Exception as e:
            logger.error(f"Failed to get bot info: {e}")

        return None

    async def run_full_diagnosis(self) -> Tuple[list[HealthCheckResult], bool]:
        """
        Run complete health check suite.

        Returns:
            Tuple of (results list, all_passed boolean)
        """
        self.results = []

        # Run checks
        self.results.append(await self.check_token_format())
        self.results.append(await self.check_api_connectivity())

        # Check for errors
        all_passed = all(r.status != "error" for r in self.results)

        return self.results, all_passed

    def format_results(self) -> str:
        """Format results as readable string."""
        lines = ["🤖 Bot Health Check Results\n"]

        for result in self.results:
            icon = {
                "ok": "✅",
                "warning": "⚠️ ",
                "error": "❌",
            }.get(result.status, "❓")

            lines.append(f"{icon} {result.name}")
            lines.append(f"   {result.message}")
            if result.duration_ms > 0:
                lines.append(f"   ({result.duration_ms:.0f}ms)")
            lines.append("")

        return "\n".join(lines)

    def format_results_table(self) -> list[Dict[str, str]]:
        """Format results for table display."""
        return [
            {
                "Check": r.name,
                "Status": r.status.upper(),
                "Message": r.message,
                "Time": f"{r.duration_ms:.0f}ms" if r.duration_ms > 0 else "-",
            }
            for r in self.results
        ]


class SelfDiagnosticBot:
    """
    Bot service with self-diagnostic capabilities.
    Runs internal health checks and reports issues.
    """

    def __init__(self, bot_name: str, bot_token: str, config_dir=None):
        """Initialize diagnostic bot."""
        self.bot_name = bot_name
        self.bot_token = bot_token
        self.config_dir = config_dir
        self.doctor = BotDoctor(bot_token)
        self.last_diagnosis_time: Optional[float] = None
        self.last_diagnosis_passed: Optional[bool] = None

    async def diagnose(self, api_call_func=None) -> Tuple[bool, str]:
        """
        Run bot diagnosis and return status.

        Args:
            api_call_func: Optional API call function

        Returns:
            Tuple of (passed, report_string)
        """
        if api_call_func:
            self.doctor.api_call_func = api_call_func

        self.last_diagnosis_time = time.time()
        results, passed = await self.doctor.run_full_diagnosis()
        self.last_diagnosis_passed = passed

        return passed, self.doctor.format_results()

    def get_diagnostic_status(self) -> Dict[str, Any]:
        """Get current diagnostic status."""
        return {
            "bot_name": self.bot_name,
            "last_diagnosis_time": self.last_diagnosis_time,
            "last_diagnosis_passed": self.last_diagnosis_passed,
            "checks_count": len(self.doctor.results),
            "latest_results": [r.to_dict() for r in self.doctor.results],
        }
