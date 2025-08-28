"""Configuration management for webcam security."""

import json
import os
from pathlib import Path
from typing import Optional
from dataclasses import dataclass


@dataclass
class Config:
    """Configuration for webcam security monitoring."""

    bot_token: str
    chat_id: str
    topic_id: Optional[str] = None
    monitoring_start_hour: int = 22  # 10 PM
    monitoring_end_hour: int = 6  # 6 AM
    grace_period: int = 25  # seconds
    min_contour_area: int = 500
    motion_threshold: int = 25 
    recording_fps: float = 30.0
    cleanup_days: int = 3
    force_monitoring: bool = False  # Force monitoring regardless of time
    device_identifier: Optional[str] = None  # Custom identifier for media messages
    media_storage_path: Optional[str] = None  # Custom path for storing media files
    headless: bool = False  # Run without GUI preview

    @classmethod
    def load(cls) -> "Config":
        """Load configuration from file."""
        config_path = cls._get_config_path()
        if not config_path.exists():
            raise FileNotFoundError(
                f"Configuration file not found at {config_path}. "
                "Please run 'webcam-security init' first."
            )

        with open(config_path, "r") as f:
            data = json.load(f)

        return cls(**data)

    def save(self) -> None:
        """Save configuration to file."""
        config_path = self._get_config_path()
        config_path.parent.mkdir(parents=True, exist_ok=True)

        with open(config_path, "w") as f:
            json.dump(self.__dict__, f, indent=2)

    @staticmethod
    def _get_config_path() -> Path:
        """Get the path to the configuration file."""
        home = Path.home()
        config_dir = home / ".webcam_security"
        return config_dir / "config.json"

    def is_configured(self) -> bool:
        """Check if the configuration is valid."""
        return bool(self.bot_token and self.chat_id)

    def get_media_storage_path(self) -> Path:
        """Get the media storage path, creating it if it doesn't exist."""
        if self.media_storage_path:
            path = Path(self.media_storage_path).expanduser()
        else:
            # Default to ~/webcam-security
            path = Path.home() / "webcam-security"
        
        # Create the directory if it doesn't exist
        path.mkdir(parents=True, exist_ok=True)
        return path
