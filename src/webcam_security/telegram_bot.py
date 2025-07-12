"""Telegram bot handler for configuration commands."""

import json
import threading
import time
from typing import Optional, Dict, Any
import requests
from datetime import datetime
import socket

from .config import Config
from .updater import SelfUpdater


class TelegramBotHandler:
    """Handles Telegram bot commands and configuration updates."""

    def __init__(self, config: Config):
        self.config = config
        self.running = False
        self.update_thread: Optional[threading.Thread] = None
        self.last_update_id = 0
        self.base_url = f"https://api.telegram.org/bot{config.bot_token}"

    def get_device_identifier(self) -> str:
        """Get device identifier, using hostname if not specified."""
        if self.config.device_identifier:
            return self.config.device_identifier
        return socket.gethostname()

    def send_message(self, text: str, parse_mode: str = "HTML") -> bool:
        """Send a message to the configured chat."""
        try:
            url = f"{self.base_url}/sendMessage"
            data = {
                "chat_id": self.config.chat_id,
                "text": text,
                "parse_mode": parse_mode,
            }
            if self.config.topic_id:
                data["message_thread_id"] = str(self.config.topic_id)

            response = requests.post(url, json=data)
            return response.status_code == 200
        except Exception as e:
            print(f"[ERROR] Failed to send message: {e}")
            return False

    def get_updates(self) -> Dict[str, Any]:
        """Get updates from Telegram."""
        try:
            url = f"{self.base_url}/getUpdates"
            params = {
                "offset": self.last_update_id + 1,
                "timeout": 30,
                "allowed_updates": ["message"],
            }
            response = requests.get(url, params=params)
            if response.status_code == 200:
                return response.json()
            return {"ok": False, "result": []}
        except Exception as e:
            print(f"[ERROR] Failed to get updates: {e}")
            return {"ok": False, "result": []}

    def handle_command(self, message: Dict[str, Any]) -> None:
        """Handle incoming commands."""
        if "text" not in message:
            return

        text = message["text"]
        chat_id = str(message["chat"]["id"])

        # Only respond to messages from the configured chat
        if chat_id != self.config.chat_id:
            return

        if text.startswith("/"):
            command = text.split()[0].lower()
            args = text.split()[1:] if len(text.split()) > 1 else []

            if command == "/start":
                self.send_start_message()
            elif command == "/status":
                self.send_status_message()
            elif command == "/help":
                self.send_help_message()
            elif command == "/force_on":
                self.force_monitoring_on()
            elif command == "/force_off":
                self.force_monitoring_off()
            elif command == "/set_hours":
                self.set_monitoring_hours(args)
            elif command == "/update":
                self.check_for_updates()

    def send_start_message(self) -> None:
        """Send welcome message."""
        device_id = self.get_device_identifier()
        message = f"""
🤖 <b>Webcam Security Bot</b>

Device: <code>{device_id}</code>
Status: {"🟢 Active" if self.config.force_monitoring else "🟡 Scheduled"}

<b>Available Commands:</b>
/status - Show current configuration
/help - Show this help message
/force_on - Force monitoring ON (ignores time schedule)
/force_off - Force monitoring OFF (returns to schedule)
/set_hours <start> <end> - Set monitoring hours (24h format)
/update - Check for software updates

<b>Current Schedule:</b>
Monitoring: {self.config.monitoring_start_hour}:00 - {self.config.monitoring_end_hour}:00
        """
        self.send_message(message.strip())

    def send_status_message(self) -> None:
        """Send current status."""
        device_id = self.get_device_identifier()
        current_hour = datetime.now().hour
        is_scheduled_active = (
            self.config.monitoring_start_hour
            <= current_hour
            < self.config.monitoring_end_hour
            if self.config.monitoring_start_hour < self.config.monitoring_end_hour
            else current_hour >= self.config.monitoring_start_hour
            or current_hour < self.config.monitoring_end_hour
        )

        status = (
            "🟢 FORCED ON"
            if self.config.force_monitoring
            else ("🟢 ACTIVE" if is_scheduled_active else "🔴 INACTIVE")
        )

        message = f"""
📊 <b>Status Report</b>

Device: <code>{device_id}</code>
Status: {status}
Current Time: {datetime.now().strftime("%H:%M:%S")}

<b>Configuration:</b>
• Monitoring Hours: {self.config.monitoring_start_hour}:00 - {self.config.monitoring_end_hour}:00
• Grace Period: {self.config.grace_period} seconds
• Cleanup Days: {self.config.cleanup_days}
• Motion Threshold: {self.config.motion_threshold}
• Min Contour Area: {self.config.min_contour_area}
        """
        self.send_message(message.strip())

    def send_help_message(self) -> None:
        """Send help message."""
        help_text = (
            "<b>📖 Command Reference</b>\n\n"
            "<b>Status & Control:</b>\n"
            "/status - Show current configuration and status\n"
            "/force_on - Force monitoring ON (ignores time schedule)\n"
            "/force_off - Force monitoring OFF (returns to schedule)\n\n"
            "<b>Configuration:</b>\n"
            "/set_hours &lt;start&gt; &lt;end&gt; - Set monitoring hours\n"
            "  Example: /set_hours 22 6 (10 PM to 6 AM)\n\n"
            "<b>System:</b>\n"
            "/update - Check for software updates\n"
            "/help - Show this help message\n\n"
            "<b>Examples:</b>\n"
            "• /set_hours 20 8 (8 PM to 8 AM)\n"
            "• /set_hours 0 24 (24/7 monitoring)"
        )
        self.send_message(help_text)

    def force_monitoring_on(self) -> None:
        """Force monitoring on."""
        self.config.force_monitoring = True
        self.config.save()
        device_id = self.get_device_identifier()
        message = f"🟢 <b>Monitoring FORCED ON</b>\n\nDevice: <code>{device_id}</code>\nTime: {datetime.now().strftime('%H:%M:%S')}\n\nMonitoring will continue regardless of schedule until /force_off is used."
        self.send_message(message)

    def force_monitoring_off(self) -> None:
        """Force monitoring off."""
        self.config.force_monitoring = False
        self.config.save()
        device_id = self.get_device_identifier()
        message = f"🔴 <b>Monitoring FORCED OFF</b>\n\nDevice: <code>{device_id}</code>\nTime: {datetime.now().strftime('%H:%M:%S')}\n\nMonitoring will now follow the normal schedule."
        self.send_message(message)

    def set_monitoring_hours(self, args: list) -> None:
        """Set monitoring hours."""
        if len(args) != 2:
            self.send_message(
                "❌ <b>Usage:</b> /set_hours <start> <end>\n\nExample: /set_hours 22 6"
            )
            return

        try:
            start_hour = int(args[0])
            end_hour = int(args[1])

            if not (0 <= start_hour <= 23 and 0 <= end_hour <= 23):
                raise ValueError("Hours must be between 0 and 23")

            self.config.monitoring_start_hour = start_hour
            self.config.monitoring_end_hour = end_hour
            self.config.save()

            device_id = self.get_device_identifier()
            message = f"✅ <b>Monitoring hours updated</b>\n\nDevice: <code>{device_id}</code>\nNew Schedule: {start_hour}:00 - {end_hour}:00\n\nConfiguration saved successfully."
            self.send_message(message)

        except ValueError as e:
            self.send_message(
                f"❌ <b>Invalid input:</b> {str(e)}\n\nUsage: /set_hours <start> <end>\nExample: /set_hours 22 6"
            )

    def check_for_updates(self) -> None:
        """Check for software updates."""
        try:
            has_update, current_version, latest_version = SelfUpdater.check_for_updates()
            
            if has_update:
                message = f"""
                🔄 <b>Update Available</b>

                Device: <code>{self.get_device_identifier()}</code>
                Current Version: <code>{current_version}</code>
                Latest Version: <code>{latest_version}</code>

                Run: <code>pip install --upgrade webcam-security</code>
                                """
                self.send_message(message.strip())

                SelfUpdater.auto_update()

                message = f"""
                ✅ <b>Update Applied</b>

                Device: <code>{self.get_device_identifier()}</code>
                Current Version: <code>{current_version}</code>
                Latest Version: <code>{latest_version}</code>
                """
                self.send_message(message.strip())
 
            elif latest_version == "unknown":
                message = f"""
                ⚠️ <b>Update Check Failed</b>

                Device: <code>{self.get_device_identifier()}</code>
                Current Version: <code>{current_version}</code>
                Error: Could not check for updates
                                """
            else:
                message = f"""
                ✅ <b>Up to Date</b>

                Device: <code>{self.get_device_identifier()}</code>
                Current Version: <code>{current_version}</code>
                Status: Latest version installed
                                """
            
            self.send_message(message.strip())
            
        except Exception as e:
            self.send_message(f"❌ <b>Update check failed:</b> {str(e)}")

    def start_polling(self) -> None:
        """Start polling for updates."""
        self.running = True
        self.update_thread = threading.Thread(target=self._poll_updates, daemon=True)
        self.update_thread.start()
        print("[INFO] Telegram bot handler started")

    def stop_polling(self) -> None:
        """Stop polling for updates."""
        self.running = False
        if self.update_thread:
            self.update_thread.join(timeout=5)
        print("[INFO] Telegram bot handler stopped")

    def _poll_updates(self) -> None:
        """Poll for updates in a separate thread."""
        while self.running:
            try:
                updates = self.get_updates()
                if updates.get("ok") and updates.get("result"):
                    for update in updates["result"]:
                        if "message" in update:
                            self.handle_command(update["message"])
                        self.last_update_id = update["update_id"]
            except Exception as e:
                print(f"[ERROR] Polling error: {e}")
                time.sleep(5)
            time.sleep(1)
