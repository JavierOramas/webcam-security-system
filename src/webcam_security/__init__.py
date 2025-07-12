"""Webcam Security - A motion detection and monitoring system."""

__version__ = "0.1.0"
__author__ = "Your Name"
__email__ = "your.email@example.com"

from .core import SecurityMonitor
from .config import Config

__all__ = ["SecurityMonitor", "Config"]
