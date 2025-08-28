"""Core security monitoring functionality."""

import cv2
import imutils
import threading
import time
import os
import requests
from datetime import datetime, timedelta
from typing import Optional
import signal
import sys
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
        
        # Auto-detect headless environment
        if 'DISPLAY' not in os.environ and not self.config.headless:
            print("[INFO] No display detected, enabling headless mode automatically.")
            self.config.headless = True

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
                    error_msg = f"Telegram send failed: {response.text}"
                    print(f"[ERROR] {error_msg}")
                    self.notify_error(error_msg, context="send_telegram_video")
        except Exception as e:
            error_msg = f"Telegram send failed: {e}"
            print(f"[ERROR] {error_msg}")
            self.notify_error(str(e), context="send_telegram_video")

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

        # Only destroy windows if not in headless mode
        if not self.config.headless:
            cv2.destroyAllWindows()
        print("[INFO] Security monitoring stopped")

    def _signal_handler(self, signum, frame) -> None:
        """Handle shutdown signals."""
        print(f"\n[INFO] Received signal {signum}, shutting down...")
        self.stop()
        sys.exit(0)

    def _record_audio(self, audio_path: str) -> None:
        """Record audio in a separate thread."""
        try:
            # Record audio for the duration of motion
            duration = self.config.grace_period
            sample_rate = 44100
            
            print(f"[INFO] Recording audio for {duration} seconds...")
            recording = sd.rec(int(duration * sample_rate), samplerate=sample_rate, channels=1)
            sd.wait()
            
            # Save the audio
            sf.write(audio_path, recording, sample_rate)
            print(f"[INFO] Audio saved to: {audio_path}")
            
        except Exception as e:
            print(f"[ERROR] Audio recording failed: {e}")

    def clean_old_files_scheduler(self) -> None:
        """Background thread to clean old files periodically."""
        while self.running:
            try:
                self.clean_old_files()
                # Sleep for 1 hour before next cleanup
                time.sleep(3600)
            except Exception as e:
                print(f"[ERROR] Cleanup scheduler error: {e}")
                time.sleep(3600)  # Continue trying

    def clean_old_files(self) -> None:
        """Clean old recording files based on cleanup_days setting."""
        try:
            media_dir = self.config.get_media_storage_path()
            cutoff_date = datetime.now() - timedelta(days=self.config.cleanup_days)
            
            cleaned_count = 0
            for file_path in media_dir.glob("*"):
                if file_path.is_file():
                    file_time = datetime.fromtimestamp(file_path.stat().st_mtime)
                    if file_time < cutoff_date:
                        file_path.unlink()
                        cleaned_count += 1
            
            if cleaned_count > 0:
                print(f"[INFO] Cleaned {cleaned_count} old files")
                
        except Exception as e:
            print(f"[ERROR] File cleanup failed: {e}")

    def motion_detector(self) -> None:
        """Main motion detection loop."""
        print("[INFO] Initializing camera...")
        
        # Initialize camera
        self.cap = cv2.VideoCapture(0)
        if not self.cap.isOpened():
            error_msg = "Could not open camera"
            print(f"[ERROR] {error_msg}")
            self.notify_error(error_msg, context="motion_detector: camera init")
            return

        print("[INFO] Camera initialized successfully")
        print("[INFO] Starting motion detection...")

        # Initialize variables
        avg = None
        recording = False
        motion_timer = None
        telegram_sent = False
        start_image_saved = False
        end_image_path = None
        first_motion_time = None
        second_image_taken = False
        timestamp = ""
        media_dir = self.config.get_media_storage_path()
        video_path = ""
        audio_path = ""
        final_path = ""
        recording_start_time = None

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
                        audio_path = ""

                    # Save start image
                    start_image_path = str(media_dir / f"start_{timestamp}.jpg")
                    cv2.imwrite(start_image_path, frame)
                    self.send_telegram_photo(start_image_path, "🚨 Motion detected! (Start)")
                    start_image_saved = True
                    first_motion_time = current_time
                    second_image_taken = False
                    
                    # Initialize recording

                    # Fix: Use proper fourcc code
                    fourcc = cv2.VideoWriter_fourcc(*"XVID")  # type: ignore
                    self.out = cv2.VideoWriter(
                        video_path,
                        fourcc,
                        self.config.recording_fps,
                        (frame.shape[1], frame.shape[0]),
                    )

                    if AUDIO_AVAILABLE:
                        self.audio_recording = True
                        self.audio_thread = threading.Thread(
                            target=self._record_audio, args=(audio_path,), daemon=True
                        )
                        self.audio_thread.start()

                    recording = True
                    telegram_sent = False
                    motion_timer = current_time
                    recording_start_time = current_time

                # Continue recording the full video
                if recording and self.out is not None:
                    self.out.write(frame)

                    # Check if we should take a second image (after 5 seconds of motion)
                    if (not second_image_taken and first_motion_time is not None and 
                        (current_time - first_motion_time) >= 5):
                        end_image_path = str(media_dir / f"end_{timestamp}.jpg")
                        cv2.imwrite(end_image_path, frame)
                        self.send_telegram_photo(end_image_path, "🚨 Motion detected! (End)")
                        second_image_taken = True

            elif recording and motion_timer is not None:
                # Motion stopped, check grace period
                if current_time - motion_timer >= self.config.grace_period:
                    print("[INFO] Motion stopped, finishing recording...")
                    
                    # Stop recording
                    if self.out is not None:
                        self.out.release()
                        self.out = None

                    # Stop audio recording
                    if AUDIO_AVAILABLE and self.audio_recording:
                        self.audio_recording = False
                        if self.audio_thread:
                            self.audio_thread.join(timeout=5)

                    # Merge audio and video if available
                    if AUDIO_AVAILABLE and FFMPEG_AVAILABLE and os.path.exists(audio_path):
                        try:
                            print("[INFO] Merging audio and video...")
                            video_stream = ffmpeg.input(video_path)
                            audio_stream = ffmpeg.input(audio_path)
                            
                            ffmpeg.output(
                                video_stream, audio_stream, final_path,
                                vcodec='copy', acodec='aac'
                            ).overwrite_output().run(quiet=True)
                            
                            # Clean up temporary files
                            os.remove(video_path)
                            os.remove(audio_path)
                            
                            # Send final video
                            self.send_telegram_video(final_path, "🎥 Motion recording complete!")
                            
                        except Exception as e:
                            print(f"[ERROR] Failed to merge audio/video: {e}")
                            # Send original video if merge fails
                            self.send_telegram_video(video_path, "🎥 Motion recording (video only)")
                    else:
                        # Send video without audio
                        self.send_telegram_video(video_path, "🎥 Motion recording (video only)")

                    # Clean up
                    recording = False
                    motion_timer = None
                    telegram_sent = False
                    start_image_saved = False
                    second_image_taken = False

            # Handle manual photo requests
            if self._manual_photo_requested:
                self._take_and_send_manual_photo(frame)
                self._manual_photo_requested = False

            # Small delay to prevent excessive CPU usage
            time.sleep(0.01)

        # Cleanup
        if self.out is not None:
            self.out.release()
        if self.cap is not None:
            self.cap.release()
        
        # Only destroy windows if not in headless mode
        if not self.config.headless:
            cv2.destroyAllWindows()
