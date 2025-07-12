"""Self-update mechanism for webcam-security."""

import subprocess
import sys
import pkg_resources
import requests
from typing import Optional, Tuple
import os


class SelfUpdater:
    """Handles self-updating functionality."""

    PACKAGE_NAME = "webcam-security"
    PYPI_URL = "https://pypi.org/pypi/webcam-security/json"

    @classmethod
    def get_current_version(cls) -> str:
        """Get current installed version."""
        try:
            return pkg_resources.get_distribution(cls.PACKAGE_NAME).version
        except pkg_resources.DistributionNotFound:
            return "unknown"

    @classmethod
    def get_latest_version(cls) -> Optional[str]:
        """Get latest version from PyPI."""
        try:
            response = requests.get(cls.PYPI_URL, timeout=10)
            if response.status_code == 200:
                return response.json()["info"]["version"]
            return None
        except Exception:
            return None

    @classmethod
    def check_for_updates(cls) -> Tuple[bool, str, str]:
        """Check if updates are available."""
        current_version = cls.get_current_version()
        latest_version = cls.get_latest_version()

        if latest_version is None:
            return False, current_version, "unknown"

        return latest_version > current_version, current_version, latest_version

    @classmethod
    def update_package(cls) -> bool:
        """Update the package to the latest version."""
        try:
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
            print(f"[ERROR] Update failed: {e.stderr}")
            return False
        except Exception as e:
            print(f"[ERROR] Update failed: {e}")
            return False

    @classmethod
    def restart_application(cls) -> None:
        """Restart the application after update."""
        print("[INFO] Restarting application after update...")
        os.execv(sys.executable, [sys.executable] + sys.argv)

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
                    print("[ERROR] Failed to install update")
                    return False
            else:
                print(f"[INFO] Already up to date (version {current_version})")
                return False

        except Exception as e:
            print(f"[ERROR] Auto-update failed: {e}")
            return False
