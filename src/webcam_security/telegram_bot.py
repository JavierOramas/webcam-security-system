"""Telegram bot handler for configuration commands."""

import json
import threading
import time
from typing import Optional, Dict, Any
import requests
from datetime import datetime
import socket
from pathlib import Path
import sys
import subprocess
import os
import cv2
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
        self.monitor = None  # Reference to SecurityMonitor

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
                "timeout": 5,  # Reduced timeout to prevent blocking
                "allowed_updates": ["message"],
            }
            response = requests.get(
                url, params=params, timeout=10
            )  # Add explicit timeout
            if response.status_code == 200:
                return response.json()
            return {"ok": False, "result": []}
        except requests.exceptions.Timeout:
            # Timeout is normal, just return empty result
            return {"ok": True, "result": []}
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
            elif command == "/set_media_path":
                self.set_media_storage_path(args)
            elif command == "/update":
                self.start_async_update()
            elif command == "/peek":
                self.take_manual_photo()
            elif command == "/record":
                self.start_manual_recording(args)
            elif command == "/restart_bot":
                self.restart_bot()
            elif command == "/restart":
                self.restart_application()
            elif command == "/stream":
                self.start_webcam_stream(args)

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
/set_media_path <path> - Set media storage path
/peek - Take manual photo and send to Telegram
/update - Check for software updates
/restart_bot - Restart bot polling thread
/restart - Restart entire application (loads new code)

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
Version: <code>{SelfUpdater.get_current_version()}</code>
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
            "/force_off - Force monitoring OFF (returns to schedule)\n"
            "/peek - Take manual photo and send to Telegram\n\n"
            "<b>Configuration:</b>\n"
            "/set_hours &lt;start&gt; &lt;end&gt; - Set monitoring hours\n"
            "  Example: /set_hours 22 6 (10 PM to 6 AM)\n"
            "/set_media_path &lt;path&gt; - Set media storage path\n"
            "  Example: /set_media_path ~/my-recordings\n\n"
            "<b>Recording:</b>\n"
            "/record [seconds] - Start manual recording now (default 60s)\n\n"
            "<b>System:</b>\n"
            "/update - Check for software updates\n"
            "/restart_bot - Restart bot polling thread\n"
            "/restart - Restart entire application (loads new code)\n"
            "/help - Show this help message\n\n"
            "<b>Examples:</b>\n"
            "• /set_hours 20 8 (8 PM to 8 AM)\n"
            "• /set_hours 0 24 (24/7 monitoring)\n"
            "• /set_media_path ~/Documents/security\n"
            "• /peek - Check what camera sees\n"
            "• /restart_bot - Restart if bot stops responding\n"
            "• /restart - Restart app after updates\n"
            "• /update_async - Background update with retries"
        )
        self.send_message(help_text)

    def start_manual_recording(self, args: list) -> None:
        """Start a manual recording regardless of motion or schedule."""
        if not self.monitor:
            self.send_message("Monitor not available. Start the monitor first.")
            return

        duration = None
        if len(args) == 1:
            try:
                duration = max(1, int(args[0]))
            except ValueError:
                self.send_message("Invalid duration. Usage: /record [seconds]")
                return

        device_id = self.get_device_identifier()
        dur_txt = f"{duration}s" if duration else f"{self.monitor.config.min_recording_seconds}s"
        message = (
            f"🎬 <b>Manual recording requested</b>\n\n"
            f"Device: <code>{device_id}</code>\n"
            f"Duration: {dur_txt}\n"
            f"Time: {datetime.now().strftime('%H:%M:%S')}\n\n"
            f"Recording will start immediately."
        )
        self.send_message(message)

        # Trigger manual recording on the monitor
        try:
            self.monitor.request_manual_recording(duration)
        except Exception as e:
            self.send_message(f"❌ Failed to request recording: {str(e)}")

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

    def set_media_storage_path(self, args: list) -> None:
        """Set media storage path."""
        if len(args) != 1:
            self.send_message(
                "❌ <b>Usage:</b> /set_media_path <path>\n\nExample: /set_media_path ~/my-recordings"
            )
            return

        try:
            new_path = args[0]
            # Test if the path can be created/accessed
            test_path = Path(new_path).expanduser()
            test_path.mkdir(parents=True, exist_ok=True)

            self.config.media_storage_path = new_path
            self.config.save()

            device_id = self.get_device_identifier()
            message = f"✅ <b>Media storage path updated</b>\n\nDevice: <code>{device_id}</code>\nNew Path: <code>{test_path}</code>\n\nConfiguration saved successfully."
            self.send_message(message)

        except Exception as e:
            self.send_message(
                f"❌ <b>Invalid path:</b> {str(e)}\n\nUsage: /set_media_path <path>\nExample: /set_media_path ~/my-recordings"
            )

    def check_for_updates(self) -> None:
        """Check for software updates."""
        try:
            has_update, current_version, latest_version = (
                SelfUpdater.check_for_updates()
            )

            if has_update:
                message = f"""
                🔄 <b>Update Available</b>

                Device: <code>{self.get_device_identifier()}</code>
                Current Version: <code>{current_version}</code>
                Latest Version: <code>{latest_version}</code>

                Run: <code>pip install --upgrade webcam-security</code>
                                """
                self.send_message(message.strip())

                import os
                import sys

                os.system(f"{sys.executable} -m pip install --upgrade webcam-security")

                has_update, current_version, latest_version = (
                    SelfUpdater.check_for_updates()
                )
                while current_version != latest_version:
                    time.sleep(10)
                    has_update, current_version, latest_version = (
                        SelfUpdater.check_for_updates()
                    )

                message = f"""
                ✅ <b>Update Applied</b>

                Device: <code>{self.get_device_identifier()}</code>
                Current Version: <code>{current_version}</code>
                Latest Version: <code>{latest_version}</code>
                """
                self.send_message(message.strip())
                return

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

    def start_async_update(self) -> None:
        """Start an asynchronous update process."""
        device_id = self.get_device_identifier()
        message = f"🔄 <b>Starting async update</b>\n\nDevice: <code>{device_id}</code>\nTime: {datetime.now().strftime('%H:%M:%S')}\n\nUpdate will run in background with retry logic."
        self.send_message(message)

        # Start update in background thread
        update_thread = SelfUpdater.auto_update_async()

        # Send completion message after a delay
        def completion_check():
            time.sleep(30)  # Wait for update to complete
            try:
                has_update, current_version, latest_version = (
                    SelfUpdater.check_for_updates()
                )
                if not has_update and current_version != "unknown":
                    completion_msg = f"✅ <b>Update completed</b>\n\nDevice: <code>{device_id}</code>\nCurrent Version: <code>{current_version}</code>\n\nUpdate process finished."
                    self.send_message(completion_msg)
                else:
                    completion_msg = f"⚠️ <b>Update status unclear</b>\n\nDevice: <code>{device_id}</code>\nCurrent Version: <code>{current_version}</code>\n\nPlease check manually."
                    self.send_message(completion_msg)
            except Exception as e:
                error_msg = f"❌ <b>Update status check failed</b>\n\nDevice: <code>{device_id}</code>\nError: {str(e)}"
                self.send_message(error_msg)

        # Start completion check in background
        completion_thread = threading.Thread(target=completion_check, daemon=True)
        completion_thread.start()



    def set_monitor(self, monitor) -> None:
        """Set reference to the SecurityMonitor for manual photo requests."""
        self.monitor = monitor

    def take_manual_photo(self) -> None:
        """Request a manual photo to be taken and sent."""
        device_id = self.get_device_identifier()
        message = f"👁️ <b>Manual peek requested</b>\n\nDevice: <code>{device_id}</code>\nTime: {datetime.now().strftime('%H:%M:%S')}\n\nTaking photo now..."
        self.send_message(message)

        # Request photo from the monitor if it's available
        if self.monitor:
            self.monitor.request_manual_photo()
        else:
            print(f"[WARNING] Monitor not available for manual photo request")

    def restart_bot(self) -> None:
        """Restart the bot polling thread."""
        device_id = self.get_device_identifier()
        message = f"🔄 <b>Restarting bot</b>\n\nDevice: <code>{device_id}</code>\nTime: {datetime.now().strftime('%H:%M:%S')}\n\nBot polling will restart."
        self.send_message(message)

        # Stop current polling
        self.stop_polling()

        # Wait a moment
        time.sleep(2)

        # Restart polling
        self.start_polling()

        # Send confirmation
        confirmation_msg = f"✅ <b>Bot restarted</b>\n\nDevice: <code>{device_id}</code>\nTime: {datetime.now().strftime('%H:%M:%S')}\n\nBot polling has been restarted successfully."
        self.send_message(confirmation_msg)

    def restart_application(self) -> None:
        """Restart the entire application process to load updated code."""
        device_id = self.get_device_identifier()
        message = f"🔄 <b>Restarting application</b>\n\nDevice: <code>{device_id}</code>\nTime: {datetime.now().strftime('%H:%M:%S')}\n\nApplication will restart to load new code."
        self.send_message(message)

        # Simple restart mechanism - just exit and let the user restart manually
        # This is safer than trying to spawn a new process from within the bot
        print(
            "[INFO] Application restart requested via Telegram. Please restart manually."
        )
        sys.exit(0)

    def start_polling(self) -> None:
        """Start polling for updates."""
        self.running = True
        self._start_polling_thread()
        print("[INFO] Telegram bot handler started")

    def _start_polling_thread(self) -> None:
        """Start the polling thread with restart capability."""

        def polling_with_restart():
            while self.running:
                try:
                    self._poll_updates()
                except Exception as e:
                    print(f"[ERROR] Polling thread crashed: {e}")
                    if self.running:
                        print("[INFO] Restarting polling thread in 10 seconds...")
                        time.sleep(10)
                        continue
                    else:
                        break

        self.update_thread = threading.Thread(target=polling_with_restart, daemon=True)
        self.update_thread.start()

    def stop_polling(self) -> None:
        """Stop polling for updates."""
        self.running = False
        if self.update_thread:
            self.update_thread.join(timeout=5)
        print("[INFO] Telegram bot handler stopped")

    def _poll_updates(self) -> None:
        """Poll for updates in a separate thread."""
        consecutive_errors = 0
        max_consecutive_errors = 5

        while self.running:
            try:
                updates = self.get_updates()
                if updates.get("ok") and updates.get("result"):
                    for update in updates["result"]:
                        if "message" in update:
                            self.handle_command(update["message"])
                        self.last_update_id = update["update_id"]

                    # Reset error counter on successful update
                    consecutive_errors = 0
                else:
                    # No updates is normal, not an error
                    consecutive_errors = 0

            except Exception as e:
                consecutive_errors += 1
                print(
                    f"[ERROR] Polling error (attempt {consecutive_errors}/{max_consecutive_errors}): {e}"
                )

                if consecutive_errors >= max_consecutive_errors:
                    print(f"[ERROR] Too many consecutive errors, stopping polling")
                    break

                # Exponential backoff for errors
                sleep_time = min(5 * (2 ** (consecutive_errors - 1)), 30)
                time.sleep(sleep_time)
                continue

            # Short sleep between polls to prevent excessive CPU usage
            time.sleep(0.5)

    def start_webcam_stream(self, args: list) -> None:
        """Handle /stream command with optional device verification."""
        requested_device = args[0] if args else self.get_device_identifier()
        current_device = self.get_device_identifier()
        
        if requested_device != current_device:
            self.send_message(f"This bot is for {current_device}, not {requested_device}")
            return
        
        self.send_message(f"Starting stream from {current_device} for 5 minutes...")
        threading.Thread(target=self._run_webcam_stream, daemon=True).start()
    
    def _run_webcam_stream(self) -> None:
        """Capture and send frames every 3 seconds for 5 minutes."""
        if not self.monitor or not self.monitor.cap or not self.monitor.cap.isOpened():
            self.send_message("Camera not available. Ensure the monitor is running.")
            return
        
        end_time = time.time() + 300  # 5 minutes
        while time.time() < end_time and self.running:
            ret, frame = self.monitor.cap.read()
            if ret:
                temp_path = "/tmp/stream_frame.jpg"
                cv2.imwrite(temp_path, frame)
                self.monitor.send_telegram_photo(temp_path, "Stream frame")
                os.remove(temp_path)
            else:
                self.send_message("Failed to capture frame.")
                break
            time.sleep(3)
        
        self.send_message("Stream ended.")
