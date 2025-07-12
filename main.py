import cv2
import imutils
import threading
import datetime
import time
import os
import requests
from datetime import datetime


def is_monitoring_hours():
    """Check if current time is between 10 PM and 6 AM"""
    current_hour = datetime.now().hour
    return current_hour >= 22 or current_hour < 6


def send_telegram_photo(image_path, caption="Motion detected!"):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
        with open(image_path, "rb") as photo:
            files = {"photo": photo}
            data = {
                "chat_id": CHAT_ID,
                "caption": caption,
            }
            if TOPIC_ID:
                data["message_thread_id"] = str(TOPIC_ID)

            response = requests.post(url, files=files, data=data)
            if response.status_code != 200:
                print(f"[ERROR] Telegram send failed: {response.text}")
    except Exception as e:
        print(f"[ERROR] Telegram send failed: {e}")

def motion_detector():
    cap = cv2.VideoCapture(0)
    time.sleep(2)

    avg = None
    recording = False
    out = None
    motion_timer = None
    telegram_sent = False
    grace_period = 60  # seconds

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame = imutils.resize(frame, width=500)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (21, 21), 0)

        if avg is None:
            avg = gray.copy().astype("float")
            continue

        cv2.accumulateWeighted(gray, avg, 0.5)
        frame_delta = cv2.absdiff(gray, cv2.convertScaleAbs(avg))

        thresh = cv2.threshold(frame_delta, 25, 255, cv2.THRESH_BINARY)[1]
        thresh = cv2.dilate(thresh, None, iterations=2)  # type: ignore
        contours = cv2.findContours(
            thresh.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        contours = imutils.grab_contours(contours)

        motion_detected = False
        for contour in contours:
            if cv2.contourArea(contour) < 500:
                continue
            motion_detected = True
            break

        current_time = time.time()

        # Only process motion detection during monitoring hours (10 PM - 6 AM)
        if motion_detected and is_monitoring_hours():
            if not recording:
                print(
                    "[INFO] Motion detected during monitoring hours. Starting recording."
                )
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                video_path = f"recording_{timestamp}.avi"
                snapshot_path = f"snapshot_{timestamp}.jpg"
                out = cv2.VideoWriter(
                    video_path,
                    cv2.VideoWriter_fourcc(*"XVID"),  # type: ignore
                    20.0,
                    (frame.shape[1], frame.shape[0]),
                )
                cv2.imwrite(snapshot_path, frame)
                send_telegram_photo(snapshot_path, "🚨 Motion detected!")
                os.remove(snapshot_path)
                telegram_sent = True
                recording = True
            if out is not None:
                out.write(frame)
            motion_timer = current_time
        elif motion_detected and not is_monitoring_hours():
            # Motion detected outside monitoring hours - just show in preview
            pass
        else:
            if (
                recording
                and motion_timer
                and (current_time - motion_timer > grace_period)
            ):
                print("[INFO] No motion for a while. Stopping recording.")
                if out is not None:
                    out.release()
                out = None
                recording = False
                telegram_sent = False
                motion_timer = None

        # Show preview (press 'q' to quit)
        # Add status text to show if monitoring is active
        status_text = (
            "MONITORING ACTIVE (10 PM - 6 AM)"
            if is_monitoring_hours()
            else "MONITORING INACTIVE"
        )
        cv2.putText(
            frame,
            status_text,
            (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 255, 0) if is_monitoring_hours() else (0, 0, 255),
            2,
        )

        cv2.imshow("Security Feed", frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    if recording and out is not None:
        out.release()
    cap.release()
    cv2.destroyAllWindows()

def clean_old_files(days_to_keep=3):
    files = os.listdir(".")
    recording_files = [f for f in files if f.startswith("recording_")]
    recording_files.sort(key=lambda x: os.path.getctime(x))
    current_time = time.time()
    threshold_time = current_time - (days_to_keep * 24 * 60 * 60)
    for file in recording_files:
        if os.path.getctime(file) < threshold_time:
            os.remove(file)

def clean_old_files_scheduler():
    while True:
        now = datetime.datetime.now()
        # Calculate next 6am
        next_run = now.replace(hour=6, minute=0, second=0, microsecond=0)
        if now >= next_run:
            # If it's already past 6am today, schedule for tomorrow
            next_run += datetime.timedelta(days=1)
        sleep_seconds = (next_run - now).total_seconds()
        time.sleep(sleep_seconds)
        clean_old_files()

# Start the scheduler in a separate thread
cleaner_thread = threading.Thread(target=clean_old_files_scheduler, daemon=True)
cleaner_thread.start()

if __name__ == "__main__":
    motion_detector()
    
