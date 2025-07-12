"""Core security monitoring functionality."""

import cv2
import imutils
import threading
import time
import os
import requests
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
import signal
import sys

from .config import Config


class SecurityMonitor:
    """Main security monitoring class."""

    def __init__(self, config: Config):
        self.config = config
        self.running = False
        self.cap: Optional[cv2.VideoCapture] = None
        self.out: Optional[cv2.VideoWriter] = None
        self.cleaner_thread: Optional[threading.Thread] = None

    def is_monitoring_hours(self) -> bool:
        """Check if current time is between monitoring hours."""
        current_hour = datetime.now().hour
        start_hour = self.config.monitoring_start_hour
        end_hour = self.config.monitoring_end_hour

        if start_hour > end_hour:  # Crosses midnight
            return current_hour >= start_hour or current_hour < end_hour
        else:
            return start_hour <= current_hour < end_hour

    def send_telegram_photo(
        self, image_path: str, caption: str = "Motion detected!"
    ) -> None:
        """Send photo to Telegram."""
        try:
            url = f"https://api.telegram.org/bot{self.config.bot_token}/sendPhoto"
            with open(image_path, "rb") as photo:
                files = {"photo": photo}
                data = {
                    "chat_id": self.config.chat_id,
                    "caption": caption,
                }
                if self.config.topic_id:
                    data["message_thread_id"] = str(self.config.topic_id)

                response = requests.post(url, files=files, data=data)
                if response.status_code != 200:
                    print(f"[ERROR] Telegram send failed: {response.text}")
        except Exception as e:
            print(f"[ERROR] Telegram send failed: {e}")

    def clean_old_files(self, days_to_keep: Optional[int] = None) -> None:
        """Clean old recording files."""
        if days_to_keep is None:
            days_to_keep = self.config.cleanup_days

        current_dir = Path.cwd()
        recording_files = list(current_dir.glob("recording_*.avi"))
        recording_files.sort(key=lambda x: x.stat().st_ctime)

        current_time = time.time()
        threshold_time = current_time - (days_to_keep * 24 * 60 * 60)

        for file in recording_files:
            if file.stat().st_ctime < threshold_time:
                try:
                    file.unlink()
                    print(f"[INFO] Removed old recording: {file}")
                except Exception as e:
                    print(f"[ERROR] Failed to remove {file}: {e}")

    def clean_old_files_scheduler(self) -> None:
        """Scheduler for cleaning old files."""
        while self.running:
            try:
                now = datetime.now()
                # Calculate next 6am
                next_run = now.replace(hour=6, minute=0, second=0, microsecond=0)
                if now >= next_run:
                    # If it's already past 6am today, schedule for tomorrow
                    next_run += timedelta(days=1)

                sleep_seconds = (next_run - now).total_seconds()
                time.sleep(sleep_seconds)

                if self.running:
                    self.clean_old_files()
            except Exception as e:
                print(f"[ERROR] Cleanup scheduler error: {e}")
                time.sleep(60)  # Wait a minute before retrying

    def motion_detector(self) -> None:
        """Main motion detection loop."""
        self.cap = cv2.VideoCapture(0)
        if not self.cap.isOpened():
            print("[ERROR] Could not open webcam")
            return

        time.sleep(2)

        avg = None
        recording = False
        motion_timer = None
        telegram_sent = False

        while self.running:
            ret, frame = self.cap.read()
            if not ret:
                print("[ERROR] Could not read frame")
                break

            frame = imutils.resize(frame, width=500)
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            gray = cv2.GaussianBlur(gray, (21, 21), 0)

            if avg is None:
                avg = gray.copy().astype("float")
                continue

            cv2.accumulateWeighted(gray, avg, 0.5)
            frame_delta = cv2.absdiff(gray, cv2.convertScaleAbs(avg))

            thresh = cv2.threshold(
                frame_delta, self.config.motion_threshold, 255, cv2.THRESH_BINARY
            )[1]
            # Fix: Use proper kernel for dilate
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
            thresh = cv2.dilate(thresh, kernel, iterations=2)

            contours = cv2.findContours(
                thresh.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )
            contours = imutils.grab_contours(contours)

            motion_detected = False
            for contour in contours:
                if cv2.contourArea(contour) < self.config.min_contour_area:
                    continue
                motion_detected = True
                break

            current_time = time.time()

            # Only process motion detection during monitoring hours
            if motion_detected and self.is_monitoring_hours():
                if not recording:
                    print(
                        "[INFO] Motion detected during monitoring hours. Starting recording."
                    )
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    video_path = f"recording_{timestamp}.avi"
                    snapshot_path = f"snapshot_{timestamp}.jpg"

                    # Fix: Use proper fourcc code
                    fourcc = cv2.VideoWriter_fourcc(*"XVID")  # type: ignore
                    self.out = cv2.VideoWriter(
                        video_path,
                        fourcc,
                        self.config.recording_fps,
                        (frame.shape[1], frame.shape[0]),
                    )

                    cv2.imwrite(snapshot_path, frame)
                    self.send_telegram_photo(snapshot_path, "🚨 Motion detected!")
                    os.remove(snapshot_path)
                    telegram_sent = True
                    recording = True

                if self.out is not None:
                    self.out.write(frame)
                motion_timer = current_time

            elif motion_detected and not self.is_monitoring_hours():
                # Motion detected outside monitoring hours - just show in preview
                pass
            else:
                if (
                    recording
                    and motion_timer
                    and (current_time - motion_timer > self.config.grace_period)
                ):
                    print("[INFO] No motion for a while. Stopping recording.")
                    if self.out is not None:
                        self.out.release()
                    self.out = None
                    recording = False
                    telegram_sent = False
                    motion_timer = None

            # Show preview with status
            status_text = (
                "MONITORING ACTIVE"
                if self.is_monitoring_hours()
                else "MONITORING INACTIVE"
            )
            color = (0, 255, 0) if self.is_monitoring_hours() else (0, 0, 255)

            cv2.putText(
                frame,
                status_text,
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                color,
                2,
            )

            cv2.imshow("Security Feed", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

        # Cleanup
        if recording and self.out is not None:
            self.out.release()
        if self.cap is not None:
            self.cap.release()
        cv2.destroyAllWindows()

    def start(self) -> None:
        """Start the security monitoring."""
        if self.running:
            print("[INFO] Security monitoring is already running")
            return

        print("[INFO] Starting security monitoring...")
        self.running = True

        # Start cleanup scheduler in background
        self.cleaner_thread = threading.Thread(
            target=self.clean_old_files_scheduler, daemon=True
        )
        self.cleaner_thread.start()

        # Set up signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        try:
            self.motion_detector()
        except KeyboardInterrupt:
            print("\n[INFO] Received interrupt signal")
        finally:
            self.stop()

    def stop(self) -> None:
        """Stop the security monitoring."""
        if not self.running:
            return

        print("[INFO] Stopping security monitoring...")
        self.running = False

        if self.out is not None:
            self.out.release()
            self.out = None

        if self.cap is not None:
            self.cap.release()
            self.cap = None

        cv2.destroyAllWindows()
        print("[INFO] Security monitoring stopped")

    def _signal_handler(self, signum, frame) -> None:
        """Handle shutdown signals."""
        print(f"\n[INFO] Received signal {signum}, shutting down...")
        self.stop()
        sys.exit(0)
