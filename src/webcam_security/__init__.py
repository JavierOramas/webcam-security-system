"""Webcam Security - A motion detection and monitoring system."""

__version__ = "0.3.3"
__author__ = "Javier Oramas"
__email__ = "javiale2000@gmail.com"

from .core import SecurityMonitor
from .config import Config

__all__ = ["SecurityMonitor", "Config"]
