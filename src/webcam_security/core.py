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
import subprocess
import shutil

# Optional audio imports
sd = None  # type: ignore
sf = None  # type: ignore
try:
    import sounddevice as sd  # type: ignore
    import soundfile as sf  # type: ignore
    AUDIO_AVAILABLE = True
except ImportError:
    AUDIO_AVAILABLE = False
    print(
        "[WARNING] Audio recording not available. Install sounddevice and soundfile for audio support."
    )

# Optional ffmpeg import (python wrapper)
ffmpeg = None  # type: ignore
try:
    import ffmpeg  # type: ignore
    FFMPEG_AVAILABLE = True
except ImportError:
    FFMPEG_AVAILABLE = False
    print(
        "[WARNING] ffmpeg-python not available. Falling back to subprocess calls if ffmpeg binary exists."
    )

# Detect ffmpeg binary availability
FFMPEG_BIN_AVAILABLE = shutil.which("ffmpeg") is not None

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
        self._manual_recording_requested = False
        self._manual_recording_duration = self.config.min_recording_seconds
        self._manual_recording_active = False
        self._ffmpeg_audio_process: Optional[subprocess.Popen] = None
        
        # Auto-detect headless environment
        if "DISPLAY" not in os.environ and not self.config.headless:
            print(
                "[INFO] No display detected, enabling headless mode automatically."
            )
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

    def request_manual_recording(self, duration_seconds: Optional[int] = None) -> None:
        """Request a manual video recording regardless of motion/schedule."""
        self._manual_recording_duration = (
            int(duration_seconds)
            if duration_seconds
            else self.config.min_recording_seconds
        )
        self._manual_recording_requested = True

    def notify_error(self, error_msg: str, context: str = "") -> None:
        """Send an error notification to Telegram chat with device identifier."""
        if self.telegram_bot:
            device_id = self.get_device_identifier()
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            message = (
                f"❌ <b>Error on {device_id}</b>\n<code>{timestamp}</code>\n"
                f"<b>Context:</b> {context}\n<b>Details:</b> {error_msg}"
            )
            try:
                self.telegram_bot.send_message(message)
            except Exception as e:
                print(f"[ERROR] Failed to send Telegram error notification: {e}")

    def send_telegram_photo(self, image_path: str, caption: str = "Motion detected!") -> None:
        """Send photo to Telegram with simple retry logic."""
        device_id = self.get_device_identifier()
        enhanced_caption = (
            f"🚨 {caption}\n\nDevice: {device_id}\nTime: "
            f"{datetime.now().strftime('%H:%M:%S')}"
        )
        url = f"https://api.telegram.org/bot{self.config.bot_token}/sendPhoto"
        data = {
            "chat_id": self.config.chat_id,
            "caption": enhanced_caption,
        }
        if self.config.topic_id:
            data["message_thread_id"] = str(self.config.topic_id)

        last_error = None
        for attempt in range(3):
            try:
                with open(image_path, "rb") as photo:
                    files = {"photo": photo}
                    response = requests.post(
                        url,
                        files=files,
                        data=data,
                        timeout=60,
                        headers={"Connection": "close"},
                    )
                if response.status_code == 200:
                    return
                last_error = f"HTTP {response.status_code}: {response.text}"
                time.sleep(2 * (attempt + 1))
            except Exception as e:
                last_error = str(e)
                time.sleep(2 * (attempt + 1))

        if last_error:
            error_msg = f"Telegram send failed: {last_error}"
            print(f"[ERROR] {error_msg}")
            self.notify_error(error_msg, context="send_telegram_photo")

    def send_telegram_video(self, video_path: str, caption: str = "Motion detected video!") -> None:
        """Send video to Telegram with simple retry logic."""
        device_id = self.get_device_identifier()
        enhanced_caption = (
            f"🎥 {caption}\n\nDevice: {device_id}\nTime: "
            f"{datetime.now().strftime('%H:%M:%S')}"
        )
        url = f"https://api.telegram.org/bot{self.config.bot_token}/sendVideo"
        data = {
            "chat_id": self.config.chat_id,
            "caption": enhanced_caption,
        }
        if self.config.topic_id:
            data["message_thread_id"] = str(self.config.topic_id)

        last_error = None
        for attempt in range(3):
            try:
                with open(video_path, "rb") as video:
                    files = {"video": video}
                    response = requests.post(
                        url,
                        files=files,
                        data=data,
                        timeout=120,
                        headers={"Connection": "close"},
                    )
                if response.status_code == 200:
                    return
                last_error = f"HTTP {response.status_code}: {response.text}"
                time.sleep(2 * (attempt + 1))
            except Exception as e:
                last_error = str(e)
                time.sleep(2 * (attempt + 1))

        if last_error:
            error_msg = f"Telegram send failed: {last_error}"
            print(f"[ERROR] {error_msg}")
            self.notify_error(error_msg, context="send_telegram_video")

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
        """Legacy sounddevice audio recorder (unused if ffmpeg binary available)."""
        try:
            duration = self.config.min_recording_seconds
            sample_rate = 44100
            print(f"[INFO] [Legacy] Recording audio for {duration} seconds...")
            recording = sd.rec(int(duration * sample_rate), samplerate=sample_rate, channels=1)
            sd.wait()
            sf.write(audio_path, recording, sample_rate)
        except Exception as e:
            print(f"[ERROR] Legacy audio recording failed: {e}")

    def _get_ffmpeg_audio_input(self) -> Optional[tuple[str, str]]:
        """Return (format, device) tuple for ffmpeg audio input based on OS, or None if unknown."""
        try:
            if sys.platform == "darwin":
                # Default microphone on macOS via avfoundation
                return ("avfoundation", ":0")
            if sys.platform.startswith("linux"):
                # Default ALSA device
                return ("alsa", "default")
            if os.name == "nt":
                # Best-effort default on Windows via dshow
                return ("dshow", "audio=Default")
        except Exception:
            pass
        return None

    def _start_ffmpeg_audio_capture(self, audio_path: str) -> None:
        """Start ffmpeg process to capture microphone audio to audio_path (wav)."""
        if not FFMPEG_BIN_AVAILABLE:
            print("[WARNING] ffmpeg binary not found. Cannot capture audio.")
            return
        audio_input = self._get_ffmpeg_audio_input()
        if audio_input is None:
            print("[WARNING] Could not determine audio input device for ffmpeg.")
            return

        fmt, device = audio_input
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            fmt,
            "-i",
            device,
            "-ac",
            "1",
            "-ar",
            "44100",
            "-c:a",
            "pcm_s16le",
            audio_path,
        ]
        try:
            print("[INFO] Starting ffmpeg audio capture...")
            self._ffmpeg_audio_process = subprocess.Popen(
                cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
        except Exception as e:
            print(f"[ERROR] Failed to start ffmpeg audio capture: {e}")
            self._ffmpeg_audio_process = None

    def _stop_ffmpeg_audio_capture(self) -> None:
        """Stop ffmpeg audio capture process gracefully."""
        proc = self._ffmpeg_audio_process
        if not proc:
            return
        try:
            if proc.stdin and not proc.stdin.closed:
                try:
                    proc.stdin.write(b"q\n")
                    proc.stdin.flush()
                except Exception:
                    pass
            proc.wait(timeout=5)
        except Exception:
            try:
                proc.terminate()
            except Exception:
                pass
        finally:
            self._ffmpeg_audio_process = None

    def _merge_video_with_audio(self, video_path: str, audio_path: Optional[str], final_path: str) -> bool:
        """Merge video with audio (or silent track) into MP4. Returns True on success."""
        if not FFMPEG_BIN_AVAILABLE:
            # Fallback: try ffmpeg-python if available
            if FFMPEG_AVAILABLE and audio_path and os.path.exists(audio_path) and ffmpeg:
                try:
                    print("[INFO] Merging with ffmpeg-python as fallback...")
                    v = ffmpeg.input(video_path)
                    a = ffmpeg.input(audio_path)
                    (
                        ffmpeg
                        .output(
                            v,
                            a,
                            final_path,
                            vcodec="libx264",
                            acodec="aac",
                            preset="veryfast",
                            crf=23,
                        )
                        .overwrite_output()
                        .run(quiet=True)
                    )
                    return os.path.exists(final_path)
                except Exception as e:
                    print(f"[ERROR] ffmpeg-python merge failed: {e}")
            # Cannot produce MP4 with audio without ffmpeg
            return False

        try:
            if audio_path and os.path.exists(audio_path):
                cmd = [
                    "ffmpeg",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-i",
                    video_path,
                    "-i",
                    audio_path,
                    "-c:v",
                    "libx264",
                    "-preset",
                    "veryfast",
                    "-crf",
                    "23",
                    "-c:a",
                    "aac",
                    "-shortest",
                    final_path,
                ]
            else:
                # Generate silent audio track to satisfy "all videos must include audio"
                cmd = [
                    "ffmpeg",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-i",
                    video_path,
                    "-f",
                    "lavfi",
                    "-i",
                    "anullsrc=r=44100:cl=mono",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "veryfast",
                    "-crf",
                    "23",
                    "-c:a",
                    "aac",
                    "-shortest",
                    final_path,
                ]
            subprocess.run(cmd, check=True)
            return os.path.exists(final_path)
        except subprocess.CalledProcessError as e:
            print(f"[ERROR] ffmpeg merge failed: {e}")
            return False

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
        manual_recording_target = None

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

            # Manual recording trigger (ignores monitoring hours)
            if self._manual_recording_requested and not recording:
                print("[INFO] Manual recording requested. Starting now.")
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                media_dir = self.config.get_media_storage_path()
                video_path = str(media_dir / f"temp_video_{timestamp}.avi")
                audio_path = str(media_dir / f"temp_audio_{timestamp}.wav")
                final_path = str(media_dir / f"recording_{timestamp}.mp4")
                start_image_path = str(media_dir / f"start_{timestamp}.jpg")
                cv2.imwrite(start_image_path, frame)
                self.send_telegram_photo(start_image_path, "🎬 Manual recording started (Start)")
                start_image_saved = True
                first_motion_time = current_time
                second_image_taken = False

                fourcc = cv2.VideoWriter_fourcc(*"XVID")  # type: ignore
                self.out = cv2.VideoWriter(
                    video_path,
                    fourcc,
                    self.config.recording_fps,
                    (frame.shape[1], frame.shape[0]),
                )

                # Start ffmpeg audio capture if possible
                if FFMPEG_BIN_AVAILABLE:
                    self._start_ffmpeg_audio_capture(audio_path)

                recording = True
                self._manual_recording_active = True
                self._manual_recording_requested = False
                recording_start_time = current_time
                manual_recording_target = self._manual_recording_duration
                motion_timer = current_time  # initialize

            # Motion-triggered recording during monitoring hours
            if motion_detected and self.is_monitoring_hours():
                if not recording:
                    audio_status = "with audio" if FFMPEG_BIN_AVAILABLE else "video only"
                    print(
                        f"[INFO] Motion detected during monitoring hours. Starting recording {audio_status}."
                    )
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

                    media_dir = self.config.get_media_storage_path()

                    video_path = str(media_dir / f"temp_video_{timestamp}.avi")
                    audio_path = str(media_dir / f"temp_audio_{timestamp}.wav")
                    final_path = str(media_dir / f"recording_{timestamp}.mp4")

                    # Save start image
                    start_image_path = str(media_dir / f"start_{timestamp}.jpg")
                    cv2.imwrite(start_image_path, frame)
                    self.send_telegram_photo(start_image_path, "🚨 Motion detected! (Start)")
                    start_image_saved = True
                    first_motion_time = current_time
                    second_image_taken = False
                    
                    # Initialize recording
                    fourcc = cv2.VideoWriter_fourcc(*"XVID")  # type: ignore
                    self.out = cv2.VideoWriter(
                        video_path,
                        fourcc,
                        self.config.recording_fps,
                        (frame.shape[1], frame.shape[0]),
                    )

                    # Start ffmpeg audio capture if possible
                    if FFMPEG_BIN_AVAILABLE:
                        self._start_ffmpeg_audio_capture(audio_path)

                    recording = True
                    telegram_sent = False
                    motion_timer = current_time
                    recording_start_time = current_time
                    self._manual_recording_active = False
                    manual_recording_target = None

                # Update last motion time if recording
                if recording:
                    motion_timer = current_time
                    # Check if we should take a second image (after 5 seconds of motion)
                    if (
                        not second_image_taken
                        and first_motion_time is not None
                        and (current_time - first_motion_time) >= 5
                    ):
                        end_image_path = str(media_dir / f"end_{timestamp}.jpg")
                        cv2.imwrite(end_image_path, frame)
                        self.send_telegram_photo(end_image_path, "🚨 Motion detected! (End)")
                        second_image_taken = True

            # Handle stopping conditions
            if recording and recording_start_time is not None:
                # Write frame continuously while recording
                if self.out is not None:
                    self.out.write(frame)

                elapsed = current_time - recording_start_time
                should_stop = False

                if self._manual_recording_active:
                    # Stop after target duration for manual recording
                    if manual_recording_target is not None and elapsed >= manual_recording_target:
                        should_stop = True
                else:
                    # Motion-triggered: stop after grace period AND minimum duration met
                    if motion_timer is not None:
                        if (
                            (current_time - motion_timer) >= self.config.grace_period
                            and elapsed >= self.config.min_recording_seconds
                        ):
                            should_stop = True

                if should_stop:
                    print("[INFO] Finishing recording...")

                    # Stop video writer
                    if self.out is not None:
                        self.out.release()
                        self.out = None

                    # Stop ffmpeg audio capture
                    self._stop_ffmpeg_audio_capture()

                    # Merge with audio (or silent track) and send
                    merged_ok = False
                    try:
                        merged_ok = self._merge_video_with_audio(
                            video_path,
                            audio_path if os.path.exists(audio_path) else None,
                            final_path,
                        )
                    except Exception as e:
                        print(f"[ERROR] Post-processing failed: {e}")

                    # Decide which file to send
                    if merged_ok and os.path.exists(final_path):
                        # Clean temp files first
                        if os.path.exists(video_path):
                            os.remove(video_path)
                        if os.path.exists(audio_path):
                            os.remove(audio_path)
                        self.send_telegram_video(final_path, "🎥 Recording complete!")
                    elif os.path.exists(video_path):
                        # Fallback: send raw video
                        self.send_telegram_video(video_path, "🎥 Recording (raw video)")
                    else:
                        self.notify_error(
                            "No video file available to send",
                            context="finish_recording",
                        )

                    # Reset state
                    recording = False
                    motion_timer = None
                    telegram_sent = False
                    start_image_saved = False
                    second_image_taken = False
                    self._manual_recording_active = False
                    manual_recording_target = None

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
