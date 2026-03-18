"""
BotFather communication layer for bot creation and management.
Interacts with Telegram's BotFather to create, configure, and manage bots.
"""

import re
import asyncio
from typing import Optional
from dataclasses import dataclass
from telethon.tl.types import Message


@dataclass
class BotCreationResult:
    """Result of bot creation attempt."""
    success: bool
    token: Optional[str] = None
    username: Optional[str] = None
    error: Optional[str] = None
    raw_response: Optional[str] = None


@dataclass
class BotPropertyUpdate:
    """Result of bot property update."""
    success: bool
    property_name: str
    property_value: str
    error: Optional[str] = None


class BotFatherClient:
    """
    Client for interacting with Telegram's BotFather.
    Handles bot creation, property modification, and metadata retrieval.
    """

    BOTFATHER_ID = 93372553  # Official BotFather user ID

    # Regex patterns for parsing BotFather responses
    TOKEN_PATTERN = re.compile(r"(\d+:[A-Za-z0-9_-]+)")
    USERNAME_PATTERN = re.compile(r"@([A-Za-z0-9_]+)")
    ERROR_INDICATORS = ["sorry", "error", "invalid", "already taken", "can't"]

    def __init__(self, telethon_client):
        """
        Initialize BotFather client.

        Args:
            telethon_client: Authenticated Telethon client for MTProto communication
        """
        self.client = telethon_client

    async def send_message(self, text: str, timeout: int = 45) -> Optional[Message]:
        """
        Send a message to BotFather and wait for response.

        Args:
            text: Command/message text to send
            timeout: Wait timeout in seconds

        Returns:
            Response message or None if timeout
        """
        import time
        try:
            # Ensure conversation exists with BotFather by fetching history first
            try:
                await self.client.get_messages(self.BOTFATHER_ID, limit=1)
            except Exception:
                pass  # Conversation might not exist yet, that's OK

            # Send message to BotFather
            sent_msg = await self.client.send_message(self.BOTFATHER_ID, text)
            sent_msg_id = sent_msg.id
            
            await asyncio.sleep(0.5)  # Wait for BotFather to process

            # Wait for response - keep checking for new messages
            start_time = time.time()
            
            while time.time() - start_time < timeout:
                try:
                    # Get recent messages from the BotFather conversation
                    messages = await self.client.get_messages(
                        self.BOTFATHER_ID, limit=20
                    )
                    
                    if messages:
                        # In a private chat with BotFather, any message with ID > our sent message
                        # MUST be from BotFather (since we're in a 1-on-1 conversation)
                        for msg in messages:
                            if msg.id > sent_msg_id:
                                # This is a response from BotFather!
                                return msg
                            
                except Exception as e:
                    pass  # Continue retrying on error

                await asyncio.sleep(1)  # Check every second

            # If we timeout, return None
            return None
        except Exception as e:
            raise RuntimeError(f"Failed to communicate with BotFather: {e}")

    def _extract_token(self, response_text: str) -> Optional[str]:
        """Extract bot token from BotFather response.
        
        Tries multiple strategies to extract token from various BotFather response formats.
        """
        if not response_text:
            return None
            
        # Strategy 1: Direct token pattern match
        match = self.TOKEN_PATTERN.search(response_text)
        if match:
            return match.group(1)
        
        # Strategy 2: Try removing common markup/formatting
        # Remove code block markers (```, `, etc.)
        cleaned = response_text.replace("```", "").replace("`", "").strip()
        match = self.TOKEN_PATTERN.search(cleaned)
        if match:
            return match.group(1)
        
        # Strategy 3: Try each line separately (token might be on its own line)
        lines = response_text.split("\n")
        for line in lines:
            line = line.strip()
            # Skip obvious headers/labels
            if line.lower() in ["token:", "bot token:", "your bot token:", "here is your token:"]:
                continue
            match = self.TOKEN_PATTERN.search(line)
            if match:
                return match.group(1)
        
        # Strategy 4: Look for digits:alphanumeric pattern (more relaxed)
        # Matches patterns like "digits:letters" anywhere in the text
        relaxed_pattern = re.compile(r'(\d+:[A-Za-z0-9_\-]{20,})')
        match = relaxed_pattern.search(response_text)
        if match:
            return match.group(1)
        
        return None

    def _extract_username(self, response_text: str) -> Optional[str]:
        """Extract bot username from BotFather response."""
        match = self.USERNAME_PATTERN.search(response_text)
        return match.group(1) if match else None

    async def test_connection(self) -> dict:
        """
        Test if we can communicate with BotFather.
        
        Returns:
            Dict with connection test result
        """
        try:
            response = await self.send_message("/start", timeout=15)
            if response:
                return {
                    "success": True,
                    "message": "Successfully connected to BotFather",
                    "response_preview": response.text[:100] if response.text else "(message with buttons)",
                }
            else:
                # Failed to get response - provide debug info
                try:
                    messages = await self.client.get_messages(self.BOTFATHER_ID, limit=10)
                    messages_info = []
                    for msg in messages:
                        msg_from = "unknown"
                        if msg.from_id:
                            if hasattr(msg.from_id, 'user_id'):
                                msg_from = f"user_{msg.from_id.user_id}"
                            elif hasattr(msg.from_id, 'channel_id'):
                                msg_from = f"channel_{msg.from_id.channel_id}"
                        
                        msg_text = msg.text[:50] if msg.text else "(no text)"
                        messages_info.append({
                            "from": msg_from,
                            "id": msg.id,
                            "text": msg_text,
                            "has_buttons": hasattr(msg, 'reply_markup') and msg.reply_markup is not None,
                        })
                    
                    return {
                        "success": False,
                        "message": "Message was sent but response not detected (check debug info below)",
                        "debug_info": {
                            "messages_count": len(messages_info),
                            "latest_messages": messages_info,
                        },
                        "tips": [
                            "Your message reached Telegram, but we couldn't detect BotFather's response",
                            "This might be a timing or parsing issue",
                            "Try 'bot sync' anyway - it might work despite this",
                            "Check the debug info above to see recent messages",
                        ]
                    }
                except Exception as debug_e:
                    return {
                        "success": False,
                        "message": "BotFather did not respond to /start",
                        "error": str(debug_e),
                        "tips": [
                            "Check your internet connection",
                            "Make sure your account is logged in",
                            "Try again in a few seconds",
                            "Verify BotFather is not blocked in your region",
                        ]
                    }
        except Exception as e:
            return {
                "success": False,
                "message": f"Error connecting to BotFather: {str(e)}",
                "error": str(e),
            }

    def _is_error_response(self, response_text: str) -> bool:
        """Check if response indicates an error."""
        lower_text = response_text.lower()
        return any(indicator in lower_text for indicator in self.ERROR_INDICATORS)

    async def create_bot(
        self, bot_name: str, bot_username: str
    ) -> BotCreationResult:
        """
        Create a new bot via BotFather.

        Args:
            bot_name: Display name for bot
            bot_username: Desired username (without @)

        Returns:
            BotCreationResult with token or error
        """
        try:
            # Step 1: Send /newbot command
            response = await self.send_message("/newbot")
            if not response or not response.text:
                return BotCreationResult(
                    success=False,
                    error="BotFather did not respond to /newbot command"
                )

            # Step 2: Send bot name
            response = await self.send_message(bot_name)
            if not response or not response.text:
                return BotCreationResult(
                    success=False,
                    error="BotFather did not respond to bot name"
                )

            if self._is_error_response(response.text):
                return BotCreationResult(
                    success=False,
                    error=f"Invalid bot name: {response.text}"
                )

            # Step 3: Send bot username
            response = await self.send_message(bot_username)
            if not response or not response.text:
                return BotCreationResult(
                    success=False,
                    error="BotFather did not respond to username"
                )

            if self._is_error_response(response.text):
                return BotCreationResult(
                    success=False,
                    error=f"Invalid or taken username: {response.text}"
                )

            # Step 4: Extract token from response
            token = self._extract_token(response.text)
            username = self._extract_username(response.text)

            if not token:
                return BotCreationResult(
                    success=False,
                    error="Could not extract token from BotFather response",
                    raw_response=response.text
                )

            return BotCreationResult(
                success=True,
                token=token,
                username=username,
                raw_response=response.text
            )

        except asyncio.TimeoutError:
            return BotCreationResult(
                success=False,
                error="Timeout communicating with BotFather"
            )
        except Exception as e:
            return BotCreationResult(
                success=False,
                error=f"Error during bot creation: {str(e)}"
            )

    async def set_bot_description(
        self, description: str
    ) -> BotPropertyUpdate:
        """
        Set bot description via BotFather.

        Args:
            description: New bot description

        Returns:
            BotPropertyUpdate result
        """
        try:
            response = await self.send_message("/setdescription")
            if not response:
                return BotPropertyUpdate(
                    success=False,
                    property_name="description",
                    property_value=description,
                    error="BotFather did not respond to /setdescription"
                )

            # Send description
            response = await self.send_message(description)
            if not response or self._is_error_response(response.text or ""):
                return BotPropertyUpdate(
                    success=False,
                    property_name="description",
                    property_value=description,
                    error=f"BotFather error: {response.text if response else 'No response'}"
                )

            return BotPropertyUpdate(
                success=True,
                property_name="description",
                property_value=description
            )

        except Exception as e:
            return BotPropertyUpdate(
                success=False,
                property_name="description",
                property_value=description,
                error=str(e)
            )

    async def set_bot_about_text(self, about_text: str) -> BotPropertyUpdate:
        """
        Set bot about text via BotFather.

        Args:
            about_text: New bot about text

        Returns:
            BotPropertyUpdate result
        """
        try:
            response = await self.send_message("/setabouttext")
            if not response:
                return BotPropertyUpdate(
                    success=False,
                    property_name="about_text",
                    property_value=about_text,
                    error="BotFather did not respond"
                )

            response = await self.send_message(about_text)
            if not response or self._is_error_response(response.text or ""):
                return BotPropertyUpdate(
                    success=False,
                    property_name="about_text",
                    property_value=about_text,
                    error=f"BotFather error: {response.text if response else 'No response'}"
                )

            return BotPropertyUpdate(
                success=True,
                property_name="about_text",
                property_value=about_text
            )

        except Exception as e:
            return BotPropertyUpdate(
                success=False,
                property_name="about_text",
                property_value=about_text,
                error=str(e)
            )

    async def set_bot_commands(
        self, commands: list[tuple[str, str]]
    ) -> BotPropertyUpdate:
        """
        Set bot command list via BotFather.

        Args:
            commands: List of (command, description) tuples

        Returns:
            BotPropertyUpdate result
        """
        try:
            response = await self.send_message("/setcommands")
            if not response:
                return BotPropertyUpdate(
                    success=False,
                    property_name="commands",
                    property_value=str(commands),
                    error="BotFather did not respond"
                )

            # Format commands for BotFather
            command_text = "\n".join(
                f"/{cmd} - {desc}" for cmd, desc in commands
            )

            response = await self.send_message(command_text)
            if not response or self._is_error_response(response.text or ""):
                return BotPropertyUpdate(
                    success=False,
                    property_name="commands",
                    property_value=str(commands),
                    error=f"BotFather error: {response.text if response else 'No response'}"
                )

            return BotPropertyUpdate(
                success=True,
                property_name="commands",
                property_value=str(commands)
            )

        except Exception as e:
            return BotPropertyUpdate(
                success=False,
                property_name="commands",
                property_value=str(commands),
                error=str(e)
            )

    async def set_privacy_mode(self, privacy_enabled: bool) -> BotPropertyUpdate:
        """
        Set bot privacy mode (affects who can use /help).

        Args:
            privacy_enabled: True to enable privacy mode

        Returns:
            BotPropertyUpdate result
        """
        try:
            response = await self.send_message("/setprivacy")
            if not response:
                return BotPropertyUpdate(
                    success=False,
                    property_name="privacy_mode",
                    property_value="enabled" if privacy_enabled else "disabled",
                    error="BotFather did not respond"
                )

            # Select mode (Enabled or Disabled)
            mode_cmd = "Enabled" if privacy_enabled else "Disabled"
            response = await self.send_message(mode_cmd)
            if not response or self._is_error_response(response.text or ""):
                return BotPropertyUpdate(
                    success=False,
                    property_name="privacy_mode",
                    property_value="enabled" if privacy_enabled else "disabled",
                    error=f"BotFather error: {response.text if response else 'No response'}"
                )

            return BotPropertyUpdate(
                success=True,
                property_name="privacy_mode",
                property_value="enabled" if privacy_enabled else "disabled"
            )

        except Exception as e:
            return BotPropertyUpdate(
                success=False,
                property_name="privacy_mode",
                property_value="enabled" if privacy_enabled else "disabled",
                error=str(e)
            )

    async def get_mybots_list(self) -> dict:
        """
        Get list of all managed bots from BotFather.
        Automatically fetches each bot's token.

        Returns:
            Dict with list of bots including tokens
        """
        try:
            response = await self.send_message("/mybots")
            if not response:
                return {"success": False, "error": "BotFather did not respond to /mybots"}

            bots_with_tokens = []
            debug_info = {
                "response_has_text": bool(response.text),
                "response_text_preview": response.text[:100] if response.text else None,
                "has_buttons": False,
                "buttons_found": 0,
                "tokens_extracted": 0,
                "username_extraction_attempts": [],
            }

            # First, try to extract usernames from buttons (most reliable)
            extracted_usernames = []
            if hasattr(response, 'reply_markup') and response.reply_markup:
                from telethon.tl.types import ReplyInlineMarkup
                if isinstance(response.reply_markup, ReplyInlineMarkup):
                    debug_info["has_buttons"] = True
                    # Extract all usernames from button texts
                    for row in response.reply_markup.rows:
                        row_buttons = row.buttons if hasattr(row, 'buttons') else []
                        for button in row_buttons:
                            if hasattr(button, 'text') and button.text:
                                username_match = self.USERNAME_PATTERN.search(button.text)
                                if username_match:
                                    username = username_match.group(1)
                                    extracted_usernames.append(username)

            debug_info["buttons_found"] = len(extracted_usernames)

            # For each username, send it to BotFather to get the token
            for username in extracted_usernames:
                attempt = {
                    "username": username,
                    "success": False,
                    "token_found": False,
                    "steps": [],
                }
                
                try:
                    # Step 1: Send /token command to tell BotFather we want a token
                    # BotFather will respond asking which bot
                    step1 = {
                        "action": "init_token_request",
                        "command": "/token",
                        "success": False,
                    }
                    
                    token_request = await self.send_message("/token")
                    if token_request:
                        step1["success"] = True
                        step1["response_preview"] = token_request.text[:80] if token_request.text else "(no text)"
                    attempt["steps"].append(step1)
                    
                    # Step 2: Send @username to select which bot to get token for
                    # BotFather now returns the actual token
                    step2 = {
                        "action": "select_bot_for_token",
                        "command": f"@{username}",
                        "success": False,
                    }
                    
                    token_response = await self.send_message(f"@{username}")
                    token = None
                    
                    if token_response:
                        step2["success"] = True
                        step2["response_preview"] = token_response.text[:80] if token_response.text else "(no text)"
                        
                        # Try extracting token from text
                        if token_response.text:
                            token = self._extract_token(token_response.text)
                            if token:
                                step2["token_found"] = True
                        
                        # If no token in text, try buttons (fallback)
                        if not token and hasattr(token_response, 'reply_markup') and token_response.reply_markup:
                            from telethon.tl.types import ReplyInlineMarkup
                            if isinstance(token_response.reply_markup, ReplyInlineMarkup):
                                for row in token_response.reply_markup.rows:
                                    row_buttons = row.buttons if hasattr(row, 'buttons') else []
                                    for button in row_buttons:
                                        if hasattr(button, 'text') and button.text:
                                            potential_token = self._extract_token(button.text)
                                            if potential_token:
                                                token = potential_token
                                                step2["token_found"] = True
                                                break
                                    if token:
                                        break
                    
                    attempt["steps"].append(step2)
                    
                    if token:
                        bots_with_tokens.append({
                            "username": username,
                            "token": token,
                            "name": f"@{username}",
                        })
                        attempt["success"] = True
                        attempt["token_found"] = True
                        debug_info["tokens_extracted"] += 1
                    else:
                        attempt["error"] = "Could not extract token from BotFather response after sending @username"
                    
                except Exception as e:
                    attempt["error"] = str(e)
                    step_error = {"action": "exception", "error": str(e)}
                    if "steps" not in attempt:
                        attempt["steps"] = []
                    attempt["steps"].append(step_error)
                
                debug_info["username_extraction_attempts"].append(attempt)
                await asyncio.sleep(1)  # Slightly longer delay between bots

            # If no bots via buttons, try text-based parsing of response text
            if not bots_with_tokens and response.text:
                lines = response.text.split("\n")
                for line in lines:
                    matches = self.USERNAME_PATTERN.findall(line)
                    if matches:
                        for username in matches:
                            if username not in [b["username"] for b in bots_with_tokens]:
                                try:
                                    token_response = await self.send_message(f"@{username}")
                                    if token_response and token_response.text:
                                        token = self._extract_token(token_response.text)
                                        if token:
                                            bots_with_tokens.append({
                                                "username": username,
                                                "token": token,
                                                "name": line.strip(),
                                            })
                                            debug_info["tokens_extracted"] += 1
                                except Exception:
                                    pass
                                await asyncio.sleep(0.8)

            # Return results
            if bots_with_tokens:
                return {
                    "success": True,
                    "bots": bots_with_tokens,
                    "count": len(bots_with_tokens),
                    "debug": debug_info,
                }

            return {
                "success": False,
                "error": "No bots found or could not extract tokens. Make sure you have bots created in @BotFather.",
                "debug": debug_info,
            }

        except Exception as e:
            return {"success": False, "error": f"Error syncing bots: {str(e)}"}
