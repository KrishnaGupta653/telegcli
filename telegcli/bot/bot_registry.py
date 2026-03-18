"""
Bot registry for managing bot profiles and metadata.
Persists bot properties (description, commands, privacy settings) in config.
"""

import time
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, asdict
from datetime import datetime


@dataclass
class BotCommand:
    """Represents a bot command."""
    name: str
    description: str

    def to_dict(self) -> Dict[str, str]:
        return {"name": self.name, "description": self.description}

    @staticmethod
    def from_dict(d: Dict[str, str]) -> "BotCommand":
        return BotCommand(name=d["name"], description=d["description"])


@dataclass
class BotMetadata:
    """Extended metadata for a bot profile."""
    description: str = ""
    about_text: str = ""
    commands: List[Dict[str, str]] = None  # List of {name, description}
    privacy_enabled: bool = True
    default_admin_rights: Dict[str, bool] = None  # Permissions dict
    created_at: float = 0
    last_modified: float = 0
    webhook_url: Optional[str] = None
    webhook_secret: Optional[str] = None

    def __post_init__(self):
        if self.commands is None:
            self.commands = []
        if self.default_admin_rights is None:
            self.default_admin_rights = {
                "can_manage_chat": False,
                "can_delete_messages": False,
                "can_manage_video_chats": False,
                "can_restrict_members": False,
                "can_promote_members": False,
                "can_change_info": False,
                "can_invite_users": False,
                "can_post_messages": False,
                "can_edit_messages": False,
                "can_pin_messages": False,
                "can_manage_topics": False,
            }
        if self.created_at == 0:
            self.created_at = time.time()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "description": self.description,
            "about_text": self.about_text,
            "commands": self.commands,
            "privacy_enabled": self.privacy_enabled,
            "default_admin_rights": self.default_admin_rights,
            "created_at": self.created_at,
            "last_modified": self.last_modified,
            "webhook_url": self.webhook_url,
            "webhook_secret": self.webhook_secret,
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "BotMetadata":
        return BotMetadata(
            description=d.get("description", ""),
            about_text=d.get("about_text", ""),
            commands=d.get("commands", []),
            privacy_enabled=d.get("privacy_enabled", True),
            default_admin_rights=d.get("default_admin_rights", {}),
            created_at=d.get("created_at", time.time()),
            last_modified=d.get("last_modified", 0),
            webhook_url=d.get("webhook_url"),
            webhook_secret=d.get("webhook_secret"),
        )


class BotRegistry:
    """
    Registry for managing bot profiles and their metadata.
    Backed by config.bot_profiles list.
    """

    def __init__(self, config):
        """
        Initialize bot registry.

        Args:
            config: Config instance
        """
        self.config = config

    def get_bot_profile(self, profile_name: str) -> Optional[Dict[str, Any]]:
        """
        Get a bot profile by name.

        Args:
            profile_name: Name of bot profile

        Returns:
            Profile dict or None
        """
        profiles = self.config.get("bot_profiles", [])
        for profile in profiles:
            if profile.get("name") == profile_name:
                return profile
        return None

    def get_bot_metadata(self, profile_name: str) -> Optional[BotMetadata]:
        """
        Get bot metadata by profile name.

        Args:
            profile_name: Name of bot profile

        Returns:
            BotMetadata instance or None
        """
        profile = self.get_bot_profile(profile_name)
        if not profile:
            return None

        metadata_dict = profile.get("metadata", {})
        return BotMetadata.from_dict(metadata_dict)

    def update_bot_metadata(
        self, profile_name: str, metadata: BotMetadata
    ) -> bool:
        """
        Update bot metadata.

        Args:
            profile_name: Name of bot profile
            metadata: Updated BotMetadata instance

        Returns:
            True if successful, False otherwise
        """
        profiles = self.config.get("bot_profiles", [])
        for profile in profiles:
            if profile.get("name") == profile_name:
                metadata.last_modified = time.time()
                profile["metadata"] = metadata.to_dict()
                self.config.set("bot_profiles", profiles)
                return True
        return False

    def set_bot_description(self, profile_name: str, description: str) -> bool:
        """Set bot description."""
        metadata = self.get_bot_metadata(profile_name)
        if not metadata:
            return False
        metadata.description = description
        return self.update_bot_metadata(profile_name, metadata)

    def set_bot_about_text(self, profile_name: str, about_text: str) -> bool:
        """Set bot about text."""
        metadata = self.get_bot_metadata(profile_name)
        if not metadata:
            return False
        metadata.about_text = about_text
        return self.update_bot_metadata(profile_name, metadata)

    def set_bot_commands(
        self, profile_name: str, commands: List[Dict[str, str]]
    ) -> bool:
        """Set bot command list."""
        metadata = self.get_bot_metadata(profile_name)
        if not metadata:
            return False
        metadata.commands = commands
        return self.update_bot_metadata(profile_name, metadata)

    def set_bot_privacy(self, profile_name: str, enabled: bool) -> bool:
        """Set bot privacy mode."""
        metadata = self.get_bot_metadata(profile_name)
        if not metadata:
            return False
        metadata.privacy_enabled = enabled
        return self.update_bot_metadata(profile_name, metadata)

    def set_webhook_config(
        self, profile_name: str, webhook_url: str, webhook_secret: str = ""
    ) -> bool:
        """Set webhook configuration."""
        metadata = self.get_bot_metadata(profile_name)
        if not metadata:
            return False
        metadata.webhook_url = webhook_url
        metadata.webhook_secret = webhook_secret
        return self.update_bot_metadata(profile_name, metadata)

    def get_all_bots(self) -> List[Dict[str, Any]]:
        """Get all bot profiles with metadata."""
        profiles = self.config.get("bot_profiles", [])
        result = []
        for profile in profiles:
            metadata = BotMetadata.from_dict(profile.get("metadata", {}))
            result.append(
                {
                    "name": profile.get("name"),
                    "token": profile.get("token"),
                    "mode": profile.get("mode", "polling"),
                    "metadata": metadata,
                }
            )
        return result

    def format_bot_info(self, profile_name: str) -> str:
        """Format bot information as readable string."""
        profile = self.get_bot_profile(profile_name)
        if not profile:
            return f"Bot '{profile_name}' not found"

        metadata = self.get_bot_metadata(profile_name)
        token = profile.get("token", "")
        masked_token = token[:10] + "..." if token else "N/A"

        lines = [
            f"📋 Bot: {profile.get('name')}",
            f"👤 Token: {masked_token}",
            f"📝 Description: {metadata.description or '(not set)'}",
            f"ℹ️  About: {metadata.about_text or '(not set)'}",
            f"🔒 Privacy: {'Enabled' if metadata.privacy_enabled else 'Disabled'}",
            f"⌚ Created: {datetime.fromtimestamp(metadata.created_at).strftime('%Y-%m-%d %H:%M:%S')}",
        ]

        if metadata.commands:
            lines.append(f"📌 Commands ({len(metadata.commands)}):")
            for cmd in metadata.commands:
                lines.append(f"   /{cmd['name']} - {cmd['description']}")

        if metadata.webhook_url:
            lines.append(f"🔗 Webhook: {metadata.webhook_url}")

        return "\n".join(lines)

    def format_commands_table(self, profile_name: str) -> List[Dict[str, str]]:
        """Get formatted commands for display in table."""
        metadata = self.get_bot_metadata(profile_name)
        if not metadata or not metadata.commands:
            return []

        return [
            {"Command": f"/{cmd['name']}", "Description": cmd['description']}
            for cmd in metadata.commands
        ]
