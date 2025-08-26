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
import subprocess
import sounddevice as sd
import soundfile as sf
import ffmpeg
import socket

# Optional audio imports
try:
    import sounddevice as sd
    import soundfile as sf

    AUDIO_AVAILABLE = True
except ImportError:
    AUDIO_AVAILABLE = False
    print(
        "[WARNING] Audio recording not available. Install sounddevice and soundfile for audio support."
    )

# Optional ffmpeg import
try:
    import ffmpeg

    FFMPEG_AVAILABLE = True
except ImportError:
    FFMPEG_AVAILABLE = False
    print(
        "[WARNING] FFmpeg not available. Install ffmpeg-python for audio/video merging."
    )

from .config import Config
from .telegram_bot import TelegramBotHandler


class SecurityMonitor:
    """Main security monitoring class."""

    def __init__(self, config: Config):
        self.config = config
        self.running = False
        self.cap: Optional[cv2.VideoCapture] = None
        self.out: Optional[cv2.VideoWriter] = None
        self.cleaner_thread: Optional[threading.Thread] = None
        self.audio_recording = False
        self.audio_thread: Optional[threading.Thread] = None
        self.telegram_bot: Optional[TelegramBotHandler] = None
        self._manual_photo_requested = False

    def is_monitoring_hours(self) -> bool:
        """Check if current time is between monitoring hours."""
        # If force monitoring is enabled, always return True
        if self.config.force_monitoring:
            return True

        current_hour = datetime.now().hour
        start_hour = self.config.monitoring_start_hour
        end_hour = self.config.monitoring_end_hour

        if start_hour > end_hour:  # Crosses midnight
            return current_hour >= start_hour or current_hour < end_hour
        else:
            return start_hour <= current_hour < end_hour

    def get_device_identifier(self) -> str:
        """Get device identifier, using hostname if not specified."""
        if self.config.device_identifier:
            return self.config.device_identifier
        return socket.gethostname()

    def request_manual_photo(self) -> None:
        """Request a manual photo to be taken and sent."""
        self._manual_photo_requested = True

    def notify_error(self, error_msg: str, context: str = "") -> None:
        """Send an error notification to Telegram chat with device identifier."""
        if self.telegram_bot:
            device_id = self.get_device_identifier()
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            message = f"❌ <b>Error on {device_id}</b>\n<code>{timestamp}</code>\n<b>Context:</b> {context}\n<b>Details:</b> {error_msg}"
            try:
                self.telegram_bot.send_message(message)
            except Exception as e:
                print(f"[ERROR] Failed to send Telegram error notification: {e}")

    def send_telegram_photo(self, image_path: str, caption: str = "Motion detected!") -> None:
        """Send photo to Telegram."""
        try:
            device_id = self.get_device_identifier()
            enhanced_caption = f"🚨 {caption}\n\nDevice: {device_id}\nTime: {datetime.now().strftime('%H:%M:%S')}"

            url = f"https://api.telegram.org/bot{self.config.bot_token}/sendPhoto"
            with open(image_path, "rb") as photo:
                files = {"photo": photo}
                data = {
                    "chat_id": self.config.chat_id,
                    "caption": enhanced_caption,
                }
                if self.config.topic_id:
                    data["message_thread_id"] = str(self.config.topic_id)

                response = requests.post(url, files=files, data=data)
                if response.status_code != 200:
                    error_msg = f"Telegram send failed: {response.text}"
                    print(f"[ERROR] {error_msg}")
                    self.notify_error(error_msg, context="send_telegram_photo")
        except Exception as e:
            error_msg = f"Telegram send failed: {e}"
            print(f"[ERROR] {error_msg}")
            self.notify_error(str(e), context="send_telegram_photo")

    def send_telegram_video(self, video_path: str, caption: str = "Motion detected video!") -> None:
        """Send video to Telegram."""
        try:
            device_id = self.get_device_identifier()
            enhanced_caption = f"🎥 {caption}\n\nDevice: {device_id}\nTime: {datetime.now().strftime('%H:%M:%S')}"

            url = f"https://api.telegram.org/bot{self.config.bot_token}/sendVideo"
            with open(video_path, "rb") as video:
                files = {"video": video}
                data = {
                    "chat_id": self.config.chat_id,
                    "caption": enhanced_caption,
                }
                if self.config.topic_id:
                    data["message_thread_id"] = str(self.config.topic_id)

                response = requests.post(url, files=files, data=data)
                if response.status_code != 200:
                    error_msg = f"Telegram video send failed: {response.text}"
                    print(f"[ERROR] {error_msg}")
                    self.notify_error(error_msg, context="send_telegram_video")
        except Exception as e:
            error_msg = f"Telegram video send failed: {e}"
            print(f"[ERROR] {error_msg}")
            self.notify_error(str(e), context="send_telegram_video")

    def clean_old_files(self, days_to_keep: Optional[int] = None) -> None:
        """Clean old recording files."""
        if days_to_keep is None:
            days_to_keep = self.config.cleanup_days

        media_dir = self.config.get_media_storage_path()
        recording_files = list(media_dir.glob("recording_*.mp4"))
        temp_video_files = list(media_dir.glob("temp_video_*.avi"))
        temp_audio_files = list(media_dir.glob("temp_audio_*.wav"))

        # Combine and sort all files by creation time
        all_files = recording_files + temp_video_files + temp_audio_files
        all_files.sort(key=lambda x: x.stat().st_ctime)

        current_time = time.time()
        threshold_time = current_time - (days_to_keep * 24 * 60 * 60)

        for file in all_files:
            if file.stat().st_ctime < threshold_time:
                try:
                    file.unlink()
                    print(f"[INFO] Removed old file: {file}")
                except Exception as e:
                    error_msg = f"Failed to remove {file}: {e}"
                    print(f"[ERROR] {error_msg}")
                    self.notify_error(str(e), context=f"clean_old_files: {file}")

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
                error_msg = f"Cleanup scheduler error: {e}"
                print(f"[ERROR] {error_msg}")
                self.notify_error(str(e), context="clean_old_files_scheduler")
                time.sleep(60)  # Wait a minute before retrying

    def _record_audio(self, audio_path: str) -> None:
        """Record audio in a separate thread."""
        if not AUDIO_AVAILABLE:
            print("[WARNING] Audio recording skipped - sounddevice not available")
            return

        try:
            samplerate = 44100
            channels = 1

            with sf.SoundFile(
                audio_path, mode="w", samplerate=samplerate, channels=channels
            ) as file:
                with sd.InputStream(samplerate=samplerate, channels=channels) as stream:
                    while self.audio_recording:
                        data, _ = stream.read(1024)
                        file.write(data)
        except Exception as e:
            error_msg = f"Audio recording failed: {e}"
            print(f"[ERROR] {error_msg}")
            self.notify_error(str(e), context="_record_audio")

    def _merge_audio_video(self) -> None:
        """Merge audio and video files into a single MP4 file using subprocess and ffmpeg CLI."""
        import subprocess

        try:
            print("[INFO] Merging audio and video...")

            # Build ffmpeg command
            cmd = [
                "ffmpeg",
                "-y",  # Overwrite output file if exists
                "-i",
                self.video_path,
                "-i",
                self.audio_path,
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-strict",
                "experimental",
                self.final_path,
            ]

            # Run ffmpeg as a subprocess
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            if result.returncode != 0:
                error_msg = f"ffmpeg failed: {result.stderr}"
                print(f"[ERROR] {error_msg}")
                self.notify_error(result.stderr, context="_merge_audio_video")
                raise RuntimeError("ffmpeg merge failed")

            # Clean up temporary files
            if os.path.exists(self.video_path):
                os.remove(self.video_path)
            if os.path.exists(self.audio_path):
                os.remove(self.audio_path)

            print(f"[INFO] Created combined recording: {self.final_path}")

        except Exception as e:
            error_msg = f"Failed to merge audio and video: {e}"
            print(f"[ERROR] {error_msg}")
            self.notify_error(str(e), context="_merge_audio_video")
            # If merging fails, keep the original files
            if os.path.exists(self.video_path):
                os.rename(self.video_path, self.final_path.replace(".mp4", ".avi"))

    def motion_detector(self) -> None:
        """Main motion detection loop."""
        # Try to open the webcam, but allow user to grant permission if needed
        self.cap = None
        max_wait_time = 60  # seconds to wait for user to allow camera access
        wait_interval = 2  # seconds between attempts
        waited = 0

        while self.cap is None or not self.cap.isOpened():
            if self.cap is not None:
                self.cap.release()
            self.cap = cv2.VideoCapture(0)
            if self.cap.isOpened():
                break
            if waited == 0:
                print(
                    "[INFO] Waiting for webcam access. Please allow camera permission if prompted..."
                )
            time.sleep(wait_interval)
            waited += wait_interval
            if waited >= max_wait_time:
                error_msg = "Could not open webcam after waiting for permission."
                print(f"[ERROR] {error_msg}")
                self.notify_error(error_msg, context="motion_detector: webcam access")
                return

        time.sleep(2)

        avg = None
        recording = False
        motion_timer = None
        telegram_sent = False
        motion_start_time = None
        motion_frames = []
        start_image_saved = False
        end_image_path = None
        first_motion_time = None
        second_image_taken = False
        start_image_saved = False
        end_image_path = None

        while self.running:
            ret, frame = self.cap.read()
            if not ret:
                error_msg = "Could not read frame"
                print(f"[ERROR] {error_msg}")
                self.notify_error(error_msg, context="motion_detector: read frame")
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
                    audio_status = "with audio" if AUDIO_AVAILABLE else "video only"
                    print(
                        f"[INFO] Motion detected during monitoring hours. Starting recording {audio_status}."
                    )
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

                    media_dir = self.config.get_media_storage_path()

                    if AUDIO_AVAILABLE and FFMPEG_AVAILABLE:
                        video_path = str(media_dir / f"temp_video_{timestamp}.avi")
                        audio_path = str(media_dir / f"temp_audio_{timestamp}.wav")
                        final_path = str(media_dir / f"recording_{timestamp}.mp4")
                    else:
                        video_path = str(media_dir / f"recording_{timestamp}.avi")
                        final_path = video_path
                        audio_path = ""  # Initialize to avoid unbound error

                    # Modify the motion detection code around line 350 (after saving the first image)
                    # Save start image
                    start_image_path = str(media_dir / f"start_{timestamp}.jpg")
                    cv2.imwrite(start_image_path, frame)
                    self.send_telegram_photo(start_image_path, "🚨 Motion detected! (Start)")
                    start_image_saved = True
                    first_motion_time = current_time
                    second_image_taken = False
                    
                    # Initialize motion clip recording
                    motion_frames = [frame.copy()]
                    motion_start_time = current_time

                    # Fix: Use proper fourcc code
                    fourcc = cv2.VideoWriter_fourcc(*"XVID")  # type: ignore
                    self.out = cv2.VideoWriter(
                        video_path,
                        fourcc,
                        self.config.recording_fps,
                        (frame.shape[1], frame.shape[0]),
                    )

                    # Start audio recording if available
                    if AUDIO_AVAILABLE:
                        self.audio_recording = True
                        self.audio_thread = threading.Thread(
                            target=self._record_audio, args=(audio_path,), daemon=True
                        )
                        self.audio_thread.start()

                        # Store paths for later merging
                        self.video_path = video_path
                        self.audio_path = audio_path
                        self.final_path = final_path

                    recording = True
                    telegram_sent = False
                
                # Store frames for the 10-second clip
                if motion_start_time and (current_time - motion_start_time <= 10.0):
                    motion_frames.append(frame.copy())
                    # Add a small delay to control frame rate
                    time.sleep(1.0 / self.config.recording_fps)
                
                # Take second image 1 second after motion detection
                if first_motion_time and not second_image_taken and (current_time - first_motion_time >= 1.0):
                    second_image_path = str(media_dir / f"second_{timestamp}.jpg")
                    cv2.imwrite(second_image_path, frame)
                    self.send_telegram_photo(second_image_path, "🚨 Motion continued! (Second)")
                    second_image_taken = True

                # Send 3-second clip after we have enough frames
                if motion_start_time and (current_time - motion_start_time > 10.0) and not telegram_sent:
                    # Create and send the 3-second clip
                    clip_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    media_dir = self.config.get_media_storage_path()
                    clip_path = str(media_dir / f"motion_clip_{clip_timestamp}.avi")
                    
                    # Create video writer for the clip
                    clip_writer = cv2.VideoWriter(
                        clip_path,
                        cv2.VideoWriter_fourcc(*"XVID"),
                        self.config.recording_fps,
                        (frame.shape[1], frame.shape[0]),
                    )
                    
                    # Write all frames to the clip
                    for f in motion_frames:
                        clip_writer.write(f)
                    clip_writer.release()
                    
                    # Send the clip to Telegram
                    self.send_telegram_video(clip_path, "🎥 Motion detected! (First 3 seconds)")
                    
                    # Save end image for the clip
                    end_image_path = str(media_dir / f"clip_end_{clip_timestamp}.jpg")
                    cv2.imwrite(end_image_path, frame)
                    
                    # Clean up the clip file after sending
                    os.remove(clip_path)
                    
                    telegram_sent = True

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

                    # Stop audio recording if available
                    if AUDIO_AVAILABLE and self.audio_recording:
                        self.audio_recording = False
                        if self.audio_thread:
                            self.audio_thread.join(timeout=5)

                    # Merge audio and video into single file if available
                    if (
                        AUDIO_AVAILABLE
                        and FFMPEG_AVAILABLE
                        and hasattr(self, "video_path")
                        and hasattr(self, "audio_path")
                        and hasattr(self, "final_path")
                    ):
                        self._merge_audio_video()
                        # For video-only, transcode to HEVC MKV if FFMPEG_AVAILABLE
                        if not AUDIO_AVAILABLE and FFMPEG_AVAILABLE and hasattr(self, "video_path") and hasattr(self, "final_path"):
                            import subprocess
                            cmd = [
                                "ffmpeg",
                                "-y",
                                "-i",
                                self.video_path,
                                "-c:v",
                                "libx265",
                                self.final_path,
                            ]
                            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                            if result.returncode == 0:
                                os.remove(self.video_path)
                            else:
                                print(f"[ERROR] Failed to transcode to HEVC MKV: {result.stderr}")
                                self.final_path = self.video_path  # Fallback to AVI

                    # Send the final video (now MKV)
                    if hasattr(self, "final_path"):
                        self.send_telegram_video(self.final_path, "📹 Full motion recording")
                    
                    # Send end image if recording has stopped
                    if start_image_saved:
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        media_dir = self.config.get_media_storage_path()
                        end_image_path = str(media_dir / f"end_{timestamp}.jpg")
                        cv2.imwrite(end_image_path, frame)
                        self.send_telegram_photo(end_image_path, "🚨 Motion ended! (End)")
                        os.remove(end_image_path)
                        start_image_saved = False

                    self.out = None
                    recording = False
                    telegram_sent = False
                    motion_timer = None
                    motion_start_time = None
                    motion_frames = []

            # Show preview with status only if not headless
            if not self.config.headless:
                if self.config.force_monitoring:
                    status_text = "MONITORING FORCED ON"
                    color = (0, 255, 255)  # Cyan for forced mode
                elif self.is_monitoring_hours():
                    status_text = "MONITORING ACTIVE"
                    color = (0, 255, 0)  # Green for active
                else:
                    status_text = "MONITORING INACTIVE"
                    color = (0, 0, 255)  # Red for inactive
            
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

        # Stop audio recording if still running
        if AUDIO_AVAILABLE and self.audio_recording:
            self.audio_recording = False
            if self.audio_thread:
                self.audio_thread.join(timeout=5)

        if self.cap is not None:
            self.cap.release()
        if not self.config.headless:
            cv2.destroyAllWindows()

        # In the stop recording block, after sending:
        # Send the final video
        if hasattr(self, "final_path"):
            self.send_telegram_video(self.final_path, "📹 Full motion recording")
            # Remove the file after upload
            if os.path.exists(self.final_path):
                os.remove(self.final_path)
                print(f"[INFO] Deleted uploaded file: {self.final_path}")

        # Send end image if recording has stopped
        if start_image_saved:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            media_dir = self.config.get_media_storage_path()
            end_image_path = str(media_dir / f"end_{timestamp}.jpg")
            cv2.imwrite(end_image_path, frame)
            self.send_telegram_photo(end_image_path, "🚨 Motion ended! (End)")
            os.remove(end_image_path)
            start_image_saved = False

        self.out = None
        recording = False
        telegram_sent = False
        motion_timer = None
        motion_start_time = None
        motion_frames = []

        # Check for manual photo request
        if self._manual_photo_requested:
            self._manual_photo_requested = False
            self._take_and_send_manual_photo(frame)

        # Show preview with status only if not headless
        if not self.config.headless:
            cv2.imshow("Security Feed", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                return

        # Cleanup
        if recording and self.out is not None:
            self.out.release()

        # Stop audio recording if still running
        if AUDIO_AVAILABLE and self.audio_recording:
            self.audio_recording = False
            if self.audio_thread:
                self.audio_thread.join(timeout=5)

        if self.cap is not None:
            self.cap.release()
            self.cap = None

        cv2.destroyAllWindows()
        print("[INFO] Security monitoring stopped")

    def _take_and_send_manual_photo(self, frame) -> None:
        """Take a manual photo and send it to Telegram."""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            media_dir = self.config.get_media_storage_path()
            snapshot_path = str(media_dir / f"manual_peek_{timestamp}.jpg")

            # Save the frame
            cv2.imwrite(snapshot_path, frame)

            # Send to Telegram
            self.send_telegram_photo(snapshot_path, "👁️ Manual peek requested!")

            # Clean up the file
            os.remove(snapshot_path)

            print(f"[INFO] Manual photo taken and sent: {snapshot_path}")

        except Exception as e:
            error_msg = f"Failed to take manual photo: {e}"
            print(f"[ERROR] {error_msg}")
            self.notify_error(str(e), context="_take_and_send_manual_photo")

    def start(self) -> None:
        """Start the security monitoring."""
        if self.running:
            print("[INFO] Security monitoring is already running")
            return

        print("[INFO] Starting security monitoring...")
        self.running = True

        # Start Telegram bot handler
        self.telegram_bot = TelegramBotHandler(self.config)
        self.telegram_bot.start_polling()

        # Connect the bot handler to this monitor for manual photo requests
        self.telegram_bot.set_monitor(self)

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

        # Stop Telegram bot handler
        if self.telegram_bot:
            self.telegram_bot.stop_polling()

        if self.out is not None:
            self.out.release()
            self.out = None

        # Stop audio recording if running
        if AUDIO_AVAILABLE and self.audio_recording:
            self.audio_recording = False
            if self.audio_thread:
                self.audio_thread.join(timeout=5)

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


class SecurityMonitor:
    """Main security monitoring class."""

    def __init__(self, config: Config):
        self.config = config
        self.running = False
        self.cap: Optional[cv2.VideoCapture] = None
        self.out: Optional[cv2.VideoWriter] = None
        self.cleaner_thread: Optional[threading.Thread] = None
        self.audio_recording = False
        self.audio_thread: Optional[threading.Thread] = None
        self.telegram_bot: Optional[TelegramBotHandler] = None
        self._manual_photo_requested = False

    def is_monitoring_hours(self) -> bool:
        """Check if current time is between monitoring hours."""
        # If force monitoring is enabled, always return True
        if self.config.force_monitoring:
            return True

        current_hour = datetime.now().hour
        start_hour = self.config.monitoring_start_hour
        end_hour = self.config.monitoring_end_hour

        if start_hour > end_hour:  # Crosses midnight
            return current_hour >= start_hour or current_hour < end_hour
        else:
            return start_hour <= current_hour < end_hour

    def get_device_identifier(self) -> str:
        """Get device identifier, using hostname if not specified."""
        if self.config.device_identifier:
            return self.config.device_identifier
        return socket.gethostname()

    def request_manual_photo(self) -> None:
        """Request a manual photo to be taken and sent."""
        self._manual_photo_requested = True

    def notify_error(self, error_msg: str, context: str = "") -> None:
        """Send an error notification to Telegram chat with device identifier."""
        if self.telegram_bot:
            device_id = self.get_device_identifier()
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            message = f"❌ <b>Error on {device_id}</b>\n<code>{timestamp}</code>\n<b>Context:</b> {context}\n<b>Details:</b> {error_msg}"
            try:
                self.telegram_bot.send_message(message)
            except Exception as e:
                print(f"[ERROR] Failed to send Telegram error notification: {e}")

    def send_telegram_photo(self, image_path: str, caption: str = "Motion detected!") -> None:
        """Send photo to Telegram."""
        try:
            device_id = self.get_device_identifier()
            enhanced_caption = f"🚨 {caption}\n\nDevice: {device_id}\nTime: {datetime.now().strftime('%H:%M:%S')}"

            url = f"https://api.telegram.org/bot{self.config.bot_token}/sendPhoto"
            with open(image_path, "rb") as photo:
                files = {"photo": photo}
                data = {
                    "chat_id": self.config.chat_id,
                    "caption": enhanced_caption,
                }
                if self.config.topic_id:
                    data["message_thread_id"] = str(self.config.topic_id)

                response = requests.post(url, files=files, data=data)
                if response.status_code != 200:
                    error_msg = f"Telegram send failed: {response.text}"
                    print(f"[ERROR] {error_msg}")
                    self.notify_error(error_msg, context="send_telegram_photo")
        except Exception as e:
            error_msg = f"Telegram send failed: {e}"
            print(f"[ERROR] {error_msg}")
            self.notify_error(str(e), context="send_telegram_photo")

    def send_telegram_video(self, video_path: str, caption: str = "Motion detected video!") -> None:
        """Send video to Telegram."""
        try:
            device_id = self.get_device_identifier()
            enhanced_caption = f"🎥 {caption}\n\nDevice: {device_id}\nTime: {datetime.now().strftime('%H:%M:%S')}"

            url = f"https://api.telegram.org/bot{self.config.bot_token}/sendVideo"
            with open(video_path, "rb") as video:
                files = {"video": video}
                data = {
                    "chat_id": self.config.chat_id,
                    "caption": enhanced_caption,
                }
                if self.config.topic_id:
                    data["message_thread_id"] = str(self.config.topic_id)

                response = requests.post(url, files=files, data=data)
                if response.status_code != 200:
                    error_msg = f"Telegram video send failed: {response.text}"
                    print(f"[ERROR] {error_msg}")
                    self.notify_error(error_msg, context="send_telegram_video")
        except Exception as e:
            error_msg = f"Telegram video send failed: {e}"
            print(f"[ERROR] {error_msg}")
            self.notify_error(str(e), context="send_telegram_video")

    def clean_old_files(self, days_to_keep: Optional[int] = None) -> None:
        """Clean old recording files."""
        if days_to_keep is None:
            days_to_keep = self.config.cleanup_days

        media_dir = self.config.get_media_storage_path()
        recording_files = list(media_dir.glob("recording_*.mp4"))
        temp_video_files = list(media_dir.glob("temp_video_*.avi"))
        temp_audio_files = list(media_dir.glob("temp_audio_*.wav"))

        # Combine and sort all files by creation time
        all_files = recording_files + temp_video_files + temp_audio_files
        all_files.sort(key=lambda x: x.stat().st_ctime)

        current_time = time.time()
        threshold_time = current_time - (days_to_keep * 24 * 60 * 60)

        for file in all_files:
            if file.stat().st_ctime < threshold_time:
                try:
                    file.unlink()
                    print(f"[INFO] Removed old file: {file}")
                except Exception as e:
                    error_msg = f"Failed to remove {file}: {e}"
                    print(f"[ERROR] {error_msg}")
                    self.notify_error(str(e), context=f"clean_old_files: {file}")

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
                error_msg = f"Cleanup scheduler error: {e}"
                print(f"[ERROR] {error_msg}")
                self.notify_error(str(e), context="clean_old_files_scheduler")
                time.sleep(60)  # Wait a minute before retrying

    def _record_audio(self, audio_path: str) -> None:
        """Record audio in a separate thread."""
        if not AUDIO_AVAILABLE:
            print("[WARNING] Audio recording skipped - sounddevice not available")
            return

        try:
            samplerate = 44100
            channels = 1

            with sf.SoundFile(
                audio_path, mode="w", samplerate=samplerate, channels=channels
            ) as file:
                with sd.InputStream(samplerate=samplerate, channels=channels) as stream:
                    while self.audio_recording:
                        data, _ = stream.read(1024)
                        file.write(data)
        except Exception as e:
            error_msg = f"Audio recording failed: {e}"
            print(f"[ERROR] {error_msg}")
            self.notify_error(str(e), context="_record_audio")

    def _merge_audio_video(self) -> None:
        """Merge audio and video files into a single MP4 file using subprocess and ffmpeg CLI."""
        import subprocess

        try:
            print("[INFO] Merging audio and video...")

            # Build ffmpeg command
            cmd = [
                "ffmpeg",
                "-y",  # Overwrite output file if exists
                "-i",
                self.video_path,
                "-i",
                self.audio_path,
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-strict",
                "experimental",
                self.final_path,
            ]

            # Run ffmpeg as a subprocess
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            if result.returncode != 0:
                error_msg = f"ffmpeg failed: {result.stderr}"
                print(f"[ERROR] {error_msg}")
                self.notify_error(result.stderr, context="_merge_audio_video")
                raise RuntimeError("ffmpeg merge failed")

            # Clean up temporary files
            if os.path.exists(self.video_path):
                os.remove(self.video_path)
            if os.path.exists(self.audio_path):
                os.remove(self.audio_path)

            print(f"[INFO] Created combined recording: {self.final_path}")

        except Exception as e:
            error_msg = f"Failed to merge audio and video: {e}"
            print(f"[ERROR] {error_msg}")
            self.notify_error(str(e), context="_merge_audio_video")
            # If merging fails, keep the original files
            if os.path.exists(self.video_path):
                os.rename(self.video_path, self.final_path.replace(".mp4", ".avi"))

    def motion_detector(self) -> None:
        """Main motion detection loop."""
        # Try to open the webcam, but allow user to grant permission if needed
        self.cap = None
        max_wait_time = 60  # seconds to wait for user to allow camera access
        wait_interval = 2  # seconds between attempts
        waited = 0

        while self.cap is None or not self.cap.isOpened():
            if self.cap is not None:
                self.cap.release()
            self.cap = cv2.VideoCapture(0)
            if self.cap.isOpened():
                break
            if waited == 0:
                print(
                    "[INFO] Waiting for webcam access. Please allow camera permission if prompted..."
                )
            time.sleep(wait_interval)
            waited += wait_interval
            if waited >= max_wait_time:
                error_msg = "Could not open webcam after waiting for permission."
                print(f"[ERROR] {error_msg}")
                self.notify_error(error_msg, context="motion_detector: webcam access")
                return

        time.sleep(2)

        avg = None
        recording = False
        motion_timer = None
        telegram_sent = False
        motion_start_time = None
        motion_frames = []
        start_image_saved = False
        end_image_path = None
        first_motion_time = None
        second_image_taken = False
        start_image_saved = False
        end_image_path = None

        while self.running:
            ret, frame = self.cap.read()
            if not ret:
                error_msg = "Could not read frame"
                print(f"[ERROR] {error_msg}")
                self.notify_error(error_msg, context="motion_detector: read frame")
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
                    audio_status = "with audio" if AUDIO_AVAILABLE else "video only"
                    print(
                        f"[INFO] Motion detected during monitoring hours. Starting recording {audio_status}."
                    )
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

                    media_dir = self.config.get_media_storage_path()

                    if AUDIO_AVAILABLE and FFMPEG_AVAILABLE:
                        video_path = str(media_dir / f"temp_video_{timestamp}.avi")
                        audio_path = str(media_dir / f"temp_audio_{timestamp}.wav")
                        final_path = str(media_dir / f"recording_{timestamp}.mp4")
                    else:
                        video_path = str(media_dir / f"recording_{timestamp}.avi")
                        final_path = video_path
                        audio_path = ""  # Initialize to avoid unbound error

                    # Modify the motion detection code around line 350 (after saving the first image)
                    # Save start image
                    start_image_path = str(media_dir / f"start_{timestamp}.jpg")
                    cv2.imwrite(start_image_path, frame)
                    self.send_telegram_photo(start_image_path, "🚨 Motion detected! (Start)")
                    start_image_saved = True
                    first_motion_time = current_time
                    second_image_taken = False
                    
                    # Initialize motion clip recording
                    motion_frames = [frame.copy()]
                    motion_start_time = current_time

                    # Fix: Use proper fourcc code
                    fourcc = cv2.VideoWriter_fourcc(*"XVID")  # type: ignore
                    self.out = cv2.VideoWriter(
                        video_path,
                        fourcc,
                        self.config.recording_fps,
                        (frame.shape[1], frame.shape[0]),
                    )

                    # Start audio recording if available
                    if AUDIO_AVAILABLE:
                        self.audio_recording = True
                        self.audio_thread = threading.Thread(
                            target=self._record_audio, args=(audio_path,), daemon=True
                        )
                        self.audio_thread.start()

                        # Store paths for later merging
                        self.video_path = video_path
                        self.audio_path = audio_path
                        self.final_path = final_path

                    recording = True
                    telegram_sent = False
                
                # Store frames for the 10-second clip
                if motion_start_time and (current_time - motion_start_time <= 10.0):
                    motion_frames.append(frame.copy())
                    # Add a small delay to control frame rate
                    time.sleep(1.0 / self.config.recording_fps)
                
                # Take second image 1 second after motion detection
                if first_motion_time and not second_image_taken and (current_time - first_motion_time >= 1.0):
                    second_image_path = str(media_dir / f"second_{timestamp}.jpg")
                    cv2.imwrite(second_image_path, frame)
                    self.send_telegram_photo(second_image_path, "🚨 Motion continued! (Second)")
                    second_image_taken = True

                # Send 3-second clip after we have enough frames
                if motion_start_time and (current_time - motion_start_time > 10.0) and not telegram_sent:
                    # Create and send the 3-second clip
                    clip_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    media_dir = self.config.get_media_storage_path()
                    clip_path = str(media_dir / f"motion_clip_{clip_timestamp}.avi")
                    
                    # Create video writer for the clip
                    clip_writer = cv2.VideoWriter(
                        clip_path,
                        cv2.VideoWriter_fourcc(*"XVID"),
                        self.config.recording_fps,
                        (frame.shape[1], frame.shape[0]),
                    )
                    
                    # Write all frames to the clip
                    for f in motion_frames:
                        clip_writer.write(f)
                    clip_writer.release()
                    
                    # Send the clip to Telegram
                    self.send_telegram_video(clip_path, "🎥 Motion detected! (First 3 seconds)")
                    
                    # Save end image for the clip
                    end_image_path = str(media_dir / f"clip_end_{clip_timestamp}.jpg")
                    cv2.imwrite(end_image_path, frame)
                    
                    # Clean up the clip file after sending
                    os.remove(clip_path)
                    
                    telegram_sent = True

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

                    # Stop audio recording if available
                    if AUDIO_AVAILABLE and self.audio_recording:
                        self.audio_recording = False
                        if self.audio_thread:
                            self.audio_thread.join(timeout=5)

                    # Merge audio and video into single file if available
                    if (
                        AUDIO_AVAILABLE
                        and FFMPEG_AVAILABLE
                        and hasattr(self, "video_path")
                        and hasattr(self, "audio_path")
                        and hasattr(self, "final_path")
                    ):
                        self._merge_audio_video()
                        # For video-only, transcode to HEVC MKV if FFMPEG_AVAILABLE
                        if not AUDIO_AVAILABLE and FFMPEG_AVAILABLE and hasattr(self, "video_path") and hasattr(self, "final_path"):
                            import subprocess
                            cmd = [
                                "ffmpeg",
                                "-y",
                                "-i",
                                self.video_path,
                                "-c:v",
                                "libx265",
                                self.final_path,
                            ]
                            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                            if result.returncode == 0:
                                os.remove(self.video_path)
                            else:
                                print(f"[ERROR] Failed to transcode to HEVC MKV: {result.stderr}")
                                self.final_path = self.video_path  # Fallback to AVI

                    # Send the final video (now MKV)
                    if hasattr(self, "final_path"):
                        self.send_telegram_video(self.final_path, "📹 Full motion recording")
                    
                    # Send end image if recording has stopped
                    if start_image_saved:
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        media_dir = self.config.get_media_storage_path()
                        end_image_path = str(media_dir / f"end_{timestamp}.jpg")
                        cv2.imwrite(end_image_path, frame)
                        self.send_telegram_photo(end_image_path, "🚨 Motion ended! (End)")
                        os.remove(end_image_path)
                        start_image_saved = False

                    self.out = None
                    recording = False
                    telegram_sent = False
                    motion_timer = None
                    motion_start_time = None
                    motion_frames = []

            # Show preview with status only if not headless
            if not self.config.headless:
                if self.config.force_monitoring:
                    status_text = "MONITORING FORCED ON"
                    color = (0, 255, 255)  # Cyan for forced mode
                elif self.is_monitoring_hours():
                    status_text = "MONITORING ACTIVE"
                    color = (0, 255, 0)  # Green for active
                else:
                    status_text = "MONITORING INACTIVE"
                    color = (0, 0, 255)  # Red for inactive
            
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

        # Stop audio recording if still running
        if AUDIO_AVAILABLE and self.audio_recording:
            self.audio_recording = False
            if self.audio_thread:
                self.audio_thread.join(timeout=5)

        if self.cap is not None:
            self.cap.release()
        if not self.config.headless:
            cv2.destroyAllWindows()

        # In the stop recording block, after sending:
        # Send the final video
        if hasattr(self, "final_path"):
            self.send_telegram_video(self.final_path, "📹 Full motion recording")
            # Remove the file after upload
            if os.path.exists(self.final_path):
                os.remove(self.final_path)
                print(f"[INFO] Deleted uploaded file: {self.final_path}")

        # Send end image if recording has stopped
        if start_image_saved:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            media_dir = self.config.get_media_storage_path()
            end_image_path = str(media_dir / f"end_{timestamp}.jpg")
            cv2.imwrite(end_image_path, frame)
            self.send_telegram_photo(end_image_path, "🚨 Motion ended! (End)")
            os.remove(end_image_path)
            start_image_saved = False

        self.out = None
        recording = False
        telegram_sent = False
        motion_timer = None
        motion_start_time = None
        motion_frames = []

        # Check for manual photo request
        if self._manual_photo_requested:
            self._manual_photo_requested = False
            self._take_and_send_manual_photo(frame)

        # Show preview with status only if not headless
        if not self.config.headless:
            cv2.imshow("Security Feed", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                return

        # Cleanup
        if recording and self.out is not None:
            self.out.release()

        # Stop audio recording if still running
        if AUDIO_AVAILABLE and self.audio_recording:
            self.audio_recording = False
            if self.audio_thread:
                self.audio_thread.join(timeout=5)

        if self.cap is not None:
            self.cap.release()
            self.cap = None

        cv2.destroyAllWindows()
        print("[INFO] Security monitoring stopped")

    def _take_and_send_manual_photo(self, frame) -> None:
        """Take a manual photo and send it to Telegram."""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            media_dir = self.config.get_media_storage_path()
            snapshot_path = str(media_dir / f"manual_peek_{timestamp}.jpg")

            # Save the frame
            cv2.imwrite(snapshot_path, frame)

            # Send to Telegram
            self.send_telegram_photo(snapshot_path, "👁️ Manual peek requested!")

            # Clean up the file
            os.remove(snapshot_path)

            print(f"[INFO] Manual photo taken and sent: {snapshot_path}")

        except Exception as e:
            error_msg = f"Failed to take manual photo: {e}"
            print(f"[ERROR] {error_msg}")
            self.notify_error(str(e), context="_take_and_send_manual_photo")

    def start(self) -> None:
        """Start the security monitoring."""
        if self.running:
            print("[INFO] Security monitoring is already running")
            return

        print("[INFO] Starting security monitoring...")
        self.running = True

        # Start Telegram bot handler
        self.telegram_bot = TelegramBotHandler(self.config)
        self.telegram_bot.start_polling()

        # Connect the bot handler to this monitor for manual photo requests
        self.telegram_bot.set_monitor(self)

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

        # Stop Telegram bot handler
        if self.telegram_bot:
            self.telegram_bot.stop_polling()

        if self.out is not None:
            self.out.release()
            self.out = None

        # Stop audio recording if running
        if AUDIO_AVAILABLE and self.audio_recording:
            self.audio_recording = False
            if self.audio_thread:
                self.audio_thread.join(timeout=5)

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


class SecurityMonitor:
    """Main security monitoring class."""

    def __init__(self, config: Config):
        self.config = config
        self.running = False
        self.cap: Optional[cv2.VideoCapture] = None
        self.out: Optional[cv2.VideoWriter] = None
        self.cleaner_thread: Optional[threading.Thread] = None
        self.audio_recording = False
        self.audio_thread: Optional[threading.Thread] = None
        self.telegram_bot: Optional[TelegramBotHandler] = None
        self._manual_photo_requested = False

    def is_monitoring_hours(self) -> bool:
        """Check if current time is between monitoring hours."""
        # If force monitoring is enabled, always return True
        if self.config.force_monitoring:
            return True

        current_hour = datetime.now().hour
        start_hour = self.config.monitoring_start_hour
        end_hour = self.config.monitoring_end_hour

        if start_hour > end_hour:  # Crosses midnight
            return current_hour >= start_hour or current_hour < end_hour
        else:
            return start_hour <= current_hour < end_hour

    def get_device_identifier(self) -> str:
        """Get device identifier, using hostname if not specified."""
        if self.config.device_identifier:
            return self.config.device_identifier
        return socket.gethostname()

    def request_manual_photo(self) -> None:
        """Request a manual photo to be taken and sent."""
        self._manual_photo_requested = True

    def notify_error(self, error_msg: str, context: str = "") -> None:
        """Send an error notification to Telegram chat with device identifier."""
        if self.telegram_bot:
            device_id = self.get_device_identifier()
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            message = f"❌ <b>Error on {device_id}</b>\n<code>{timestamp}</code>\n<b>Context:</b> {context}\n<b>Details:</b> {error_msg}"
            try:
                self.telegram_bot.send_message(message)
            except Exception as e:
                print(f"[ERROR] Failed to send Telegram error notification: {e}")

    def send_telegram_photo(self, image_path: str, caption: str = "Motion detected!") -> None:
        """Send photo to Telegram."""
        try:
            device_id = self.get_device_identifier()
            enhanced_caption = f"🚨 {caption}\n\nDevice: {device_id}\nTime: {datetime.now().strftime('%H:%M:%S')}"

            url = f"https://api.telegram.org/bot{self.config.bot_token}/sendPhoto"
            with open(image_path, "rb") as photo:
                files = {"photo": photo}
                data = {
                    "chat_id": self.config.chat_id,
                    "caption": enhanced_caption,
                }
                if self.config.topic_id:
                    data["message_thread_id"] = str(self.config.topic_id)

                response = requests.post(url, files=files, data=data)
                if response.status_code != 200:
                    error_msg = f"Telegram send failed: {response.text}"
                    print(f"[ERROR] {error_msg}")
                    self.notify_error(error_msg, context="send_telegram_photo")
        except Exception as e:
            error_msg = f"Telegram send failed: {e}"
            print(f"[ERROR] {error_msg}")
            self.notify_error(str(e), context="send_telegram_photo")

    def send_telegram_video(self, video_path: str, caption: str = "Motion detected video!") -> None:
        """Send video to Telegram."""
        try:
            device_id = self.get_device_identifier()
            enhanced_caption = f"🎥 {caption}\n\nDevice: {device_id}\nTime: {datetime.now().strftime('%H:%M:%S')}"

            url = f"https://api.telegram.org/bot{self.config.bot_token}/sendVideo"
            with open(video_path, "rb") as video:
                files = {"video": video}
                data = {
                    "chat_id": self.config.chat_id,
                    "caption": enhanced_caption,
                }
                if self.config.topic_id:
                    data["message_thread_id"] = str(self.config.topic_id)

                response = requests.post(url, files=files, data=data)
                if response.status_code != 200:
                    error_msg = f"Telegram video send failed: {response.text}"
                    print(f"[ERROR] {error_msg}")
                    self.notify_error(error_msg, context="send_telegram_video")
        except Exception as e:
            error_msg = f"Telegram video send failed: {e}"
            print(f"[ERROR] {error_msg}")
            self.notify_error(str(e), context="send_telegram_video")

    def clean_old_files(self, days_to_keep: Optional[int] = None) -> None:
        """Clean old recording files."""
        if days_to_keep is None:
            days_to_keep = self.config.cleanup_days

        media_dir = self.config.get_media_storage_path()
        recording_files = list(media_dir.glob("recording_*.mp4"))
        temp_video_files = list(media_dir.glob("temp_video_*.avi"))
        temp_audio_files = list(media_dir.glob("temp_audio_*.wav"))

        # Combine and sort all files by creation time
        all_files = recording_files + temp_video_files + temp_audio_files
        all_files.sort(key=lambda x: x.stat().st_ctime)

        current_time = time.time()
        threshold_time = current_time - (days_to_keep * 24 * 60 * 60)

        for file in all_files:
            if file.stat().st_ctime < threshold_time:
                try:
                    file.unlink()
                    print(f"[INFO] Removed old file: {file}")
                except Exception as e:
                    error_msg = f"Failed to remove {file}: {e}"
                    print(f"[ERROR] {error_msg}")
                    self.notify_error(str(e), context=f"clean_old_files: {file}")

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
                error_msg = f"Cleanup scheduler error: {e}"
                print(f"[ERROR] {error_msg}")
                self.notify_error(str(e), context="clean_old_files_scheduler")
                time.sleep(60)  # Wait a minute before retrying

    def _record_audio(self, audio_path: str) -> None:
        """Record audio in a separate thread."""
        if not AUDIO_AVAILABLE:
            print("[WARNING] Audio recording skipped - sounddevice not available")
            return

        try:
            samplerate = 44100
            channels = 1

            with sf.SoundFile(
                audio_path, mode="w", samplerate=samplerate, channels=channels
            ) as file:
                with sd.InputStream(samplerate=samplerate, channels=channels) as stream:
                    while self.audio_recording:
                        data, _ = stream.read(1024)
                        file.write(data)
        except Exception as e:
            error_msg = f"Audio recording failed: {e}"
            print(f"[ERROR] {error_msg}")
            self.notify_error(str(e), context="_record_audio")

    def _merge_audio_video(self) -> None:
        """Merge audio and video files into a single MP4 file using subprocess and ffmpeg CLI."""
        import subprocess

        try:
            print("[INFO] Merging audio and video...")

            # Build ffmpeg command
            cmd = [
                "ffmpeg",
                "-y",  # Overwrite output file if exists
                "-i",
                self.video_path,
                "-i",
                self.audio_path,
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-strict",
                "experimental",
                self.final_path,
            ]

            # Run ffmpeg as a subprocess
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            if result.returncode != 0:
                error_msg = f"ffmpeg failed: {result.stderr}"
                print(f"[ERROR] {error_msg}")
                self.notify_error(result.stderr, context="_merge_audio_video")
                raise RuntimeError("ffmpeg merge failed")

            # Clean up temporary files
            if os.path.exists(self.video_path):
                os.remove(self.video_path)
            if os.path.exists(self.audio_path):
                os.remove(self.audio_path)

            print(f"[INFO] Created combined recording: {self.final_path}")

        except Exception as e:
            error_msg = f"Failed to merge audio and video: {e}"
            print(f"[ERROR] {error_msg}")
            self.notify_error(str(e), context="_merge_audio_video")
            # If merging fails, keep the original files
            if os.path.exists(self.video_path):
                os.rename(self.video_path, self.final_path.replace(".mp4", ".avi"))

    def motion_detector(self) -> None:
        """Main motion detection loop."""
        # Try to open the webcam, but allow user to grant permission if needed
        self.cap = None
        max_wait_time = 60  # seconds to wait for user to allow camera access
        wait_interval = 2  # seconds between attempts
        waited = 0

        while self.cap is None or not self.cap.isOpened():
            if self.cap is not None:
                self.cap.release()
            self.cap = cv2.VideoCapture(0)
            if self.cap.isOpened():
                break
            if waited == 0:
                print(
                    "[INFO] Waiting for webcam access. Please allow camera permission if prompted..."
                )
            time.sleep(wait_interval)
            waited += wait_interval
            if waited >= max_wait_time:
                error_msg = "Could not open webcam after waiting for permission."
                print(f"[ERROR] {error_msg}")
                self.notify_error(error_msg, context="motion_detector: webcam access")
                return

        time.sleep(2)

        avg = None
        recording = False
        motion_timer = None
        telegram_sent = False
        motion_start_time = None
        motion_frames = []
        start_image_saved = False
        end_image_path = None
        first_motion_time = None
        second_image_taken = False
        start_image_saved = False
        end_image_path = None

        while self.running:
            ret, frame = self.cap.read()
            if not ret:
                error_msg = "Could not read frame"
                print(f"[ERROR] {error_msg}")
                self.notify_error(error_msg, context="motion_detector: read frame")
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
                    audio_status = "with audio" if AUDIO_AVAILABLE else "video only"
                    print(
                        f"[INFO] Motion detected during monitoring hours. Starting recording {audio_status}."
                    )
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

                    media_dir = self.config.get_media_storage_path()

                    if AUDIO_AVAILABLE and FFMPEG_AVAILABLE:
                        video_path = str(media_dir / f"temp_video_{timestamp}.avi")
                        audio_path = str(media_dir / f"temp_audio_{timestamp}.wav")
                        final_path = str(media_dir / f"recording_{timestamp}.mp4")
                    else:
                        video_path = str(media_dir / f"recording_{timestamp}.avi")
                        final_path = video_path
                        audio_path = ""  # Initialize to avoid unbound error

                    # Modify the motion detection code around line 350 (after saving the first image)
                    # Save start image
                    start_image_path = str(media_dir / f"start_{timestamp}.jpg")
                    cv2.imwrite(start_image_path, frame)
                    self.send_telegram_photo(start_image_path, "🚨 Motion detected! (Start)")
                    start_image_saved = True
                    first_motion_time = current_time
                    second_image_taken = False
                    
                    # Initialize motion clip recording
                    motion_frames = [frame.copy()]
                    motion_start_time = current_time

                    # Fix: Use proper fourcc code
                    fourcc = cv2.VideoWriter_fourcc(*"XVID")  # type: ignore
                    self.out = cv2.VideoWriter(
                        video_path,
                        fourcc,
                        self.config.recording_fps,
                        (frame.shape[1], frame.shape[0]),
                    )

                    # Start audio recording if available
                    if AUDIO_AVAILABLE:
                        self.audio_recording = True
                        self.audio_thread = threading.Thread(
                            target
