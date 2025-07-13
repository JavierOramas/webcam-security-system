"""Self-update mechanism for webcam-security."""

import subprocess
import sys
import requests
from typing import Optional, Tuple
import os
import threading
import time


class SelfUpdater:
    """Handles self-updating functionality."""

    PACKAGE_NAME = "webcam-security"
    PYPI_URL = "https://pypi.org/pypi/webcam-security/json"
    MAX_RETRIES = 5
    RETRY_DELAY = 10  # seconds between retries

    @classmethod
    def get_current_version(cls) -> str:
        """Get current installed version."""
        try:
            # Try importlib.metadata first (Python 3.8+)
            import importlib.metadata

            return importlib.metadata.version(cls.PACKAGE_NAME)
        except ImportError:
            try:
                # Fallback to pkg_resources
                import pkg_resources

                return pkg_resources.get_distribution(cls.PACKAGE_NAME).version
            except ImportError:
                pass
        except Exception:
            pass

        # If all else fails, try to get version from the package itself
        try:
            from webcam_security import __version__

            return __version__
        except ImportError:
            pass

        return "unknown"

    @classmethod
    def get_latest_version(cls) -> Optional[str]:
        """Get latest version from PyPI."""
        try:
            response = requests.get(cls.PYPI_URL, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if "info" in data and "version" in data["info"]:
                    return data["info"]["version"]
                else:
                    print(f"[DEBUG] Unexpected PyPI response format: {data}")
                    return None
            else:
                print(f"[DEBUG] PyPI request failed with status {response.status_code}")
                return None
        except Exception as e:
            print(f"[DEBUG] Failed to get latest version: {e}")
            return None

    @classmethod
    def check_for_updates(cls) -> Tuple[bool, str, str]:
        """Check if updates are available."""
        current_version = cls.get_current_version()
        latest_version = cls.get_latest_version()

        if latest_version is None:
            return False, current_version, "unknown"

        if current_version == "unknown":
            return False, current_version, latest_version

        # Compare versions properly
        try:
            from packaging import version as pkg_version

            has_update = pkg_version.parse(latest_version) > pkg_version.parse(
                current_version
            )
        except ImportError:
            # Fallback to string comparison if packaging is not available
            has_update = latest_version > current_version

        return has_update, current_version, latest_version

    @classmethod
    def update_package(cls) -> bool:
        """Update the package to the latest version with retry logic."""
        for attempt in range(cls.MAX_RETRIES):
            try:
                print(f"[INFO] Update attempt {attempt + 1}/{cls.MAX_RETRIES}")

                # Use pip to upgrade the package
                result = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "pip",
                        "install",
                        "--upgrade",
                        cls.PACKAGE_NAME,
                    ],
                    capture_output=True,
                    text=True,
                    check=True,
                )

                print(f"[INFO] Update successful: {result.stdout}")
                return True

            except subprocess.CalledProcessError as e:
                print(f"[ERROR] Update attempt {attempt + 1} failed: {e.stderr}")
                if attempt < cls.MAX_RETRIES - 1:
                    print(f"[INFO] Retrying in {cls.RETRY_DELAY} seconds...")
                    time.sleep(cls.RETRY_DELAY)
                else:
                    print(f"[ERROR] All {cls.MAX_RETRIES} update attempts failed")
                    return False
            except Exception as e:
                print(f"[ERROR] Update attempt {attempt + 1} failed: {e}")
                if attempt < cls.MAX_RETRIES - 1:
                    print(f"[INFO] Retrying in {cls.RETRY_DELAY} seconds...")
                    time.sleep(cls.RETRY_DELAY)
                else:
                    print(f"[ERROR] All {cls.MAX_RETRIES} update attempts failed")
                    return False

        return False

    @classmethod
    def restart_application(cls) -> None:
        """Restart the application after update."""
        print("[INFO] Restarting application after update...")
        os.execv(sys.executable, [sys.executable] + sys.argv)

    @classmethod
    def debug_info(cls) -> None:
        """Print debug information about the updater."""
        current_version = cls.get_current_version()
        latest_version = cls.get_latest_version()

        print(f"[DEBUG] Package name: {cls.PACKAGE_NAME}")
        print(f"[DEBUG] PyPI URL: {cls.PYPI_URL}")
        print(f"[DEBUG] Current version: {current_version}")
        print(f"[DEBUG] Latest version: {latest_version}")

        if latest_version:
            try:
                from packaging import version as pkg_version

                has_update = pkg_version.parse(latest_version) > pkg_version.parse(
                    current_version
                )
                print(f"[DEBUG] Has update: {has_update}")
            except ImportError:
                has_update = latest_version > current_version
                print(f"[DEBUG] Has update (string comparison): {has_update}")

    @classmethod
    def auto_update(cls) -> bool:
        """Automatically check for updates and install if available."""
        try:
            has_update, current_version, latest_version = cls.check_for_updates()

            if has_update:
                print(f"[INFO] Update available: {current_version} -> {latest_version}")
                print("[INFO] Installing update...")

                if cls.update_package():
                    print("[INFO] Update installed successfully!")
                    print("[INFO] Restarting to apply changes...")
                    cls.restart_application()
                    return True
                else:
                    print("[ERROR] Failed to install update after all retries")
                    return False
            else:
                print(f"[INFO] Already up to date (version {current_version})")
                return False

        except Exception as e:
            print(f"[ERROR] Auto-update failed: {e}")
            return False

    @classmethod
    def auto_update_async(cls) -> threading.Thread:
        """Start auto-update in a separate thread."""

        def update_thread():
            try:
                cls.auto_update()
            except Exception as e:
                print(f"[ERROR] Async update thread failed: {e}")

        thread = threading.Thread(target=update_thread, daemon=True)
        thread.start()
        return thread
