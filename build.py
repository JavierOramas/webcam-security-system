#!/usr/bin/env python3
"""Fast build script for webcam-security package using UV."""

import subprocess
import sys
import os
import shutil
from pathlib import Path
import time


def run_command(cmd, description, check=True):
    """Run a command and handle errors, streaming output live."""
    print(f"🔄 {description}...")
    import shlex
    import threading
    import sys
    import time

    start_time = time.time()
    process = subprocess.Popen(
        shlex.split(cmd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        universal_newlines=True,
    )

    def stream(pipe, prefix):
        for line in iter(pipe.readline, ""):
            print(f"{prefix}{line}", end="")
        pipe.close()

    threads = [
        threading.Thread(target=stream, args=(process.stdout, "")),
        threading.Thread(target=stream, args=(process.stderr, "[stderr] ")),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    process.wait()
    elapsed = time.time() - start_time
    if process.returncode != 0:
        print(
            f"❌ Error ({elapsed:.2f}s): Command failed with exit code {process.returncode}"
        )
        if check:
            return False
    else:
        print(f"✅ {description} completed ({elapsed:.2f}s)")
    return True


def check_uv_installed():
    """Check if UV is installed."""
    if shutil.which("uv") is None:
        print("❌ UV is not installed. Installing UV...")
        install_cmd = "curl -LsSf https://astral.sh/uv/install.sh | sh"
        if not run_command(install_cmd, "Installing UV"):
            print(
                "❌ Failed to install UV. Please install manually: https://docs.astral.sh/uv/getting-started/installation/"
            )
            return False
        print("✅ UV installed successfully")
    return True


def main():
    """Main build function."""
    print("🚀 Building webcam-security package with UV...")

    if not check_uv_installed():
        return False

    # Clean previous builds
    if not run_command(
        "rm -rf build/ dist/ *.egg-info/ .pytest_cache/ .coverage htmlcov/",
        "Cleaning previous builds",
    ):
        return False

    # Install build dependencies with UV (faster than pip)
    if not run_command(
        "uv pip install hatchling build twine", "Installing build dependencies"
    ):
        return False

    # # Build wheel and source distribution in one command
    # if not run_command("uv run python -m build", "Building package"):
    #     return False
    # os.system("uv run python -m build")

    # Check the built package
    if not run_command("uv run python -m twine check dist/*", "Checking package"):
        return False

    print("\n🎉 Package built successfully!")
    print("\n📦 Built files:")
    for file in Path("dist").glob("*"):
        size = file.stat().st_size / 1024  # KB
        print(f"   {file} ({size:.1f} KB)")

    print("\n📋 Next steps:")
    print("1. Test the package: uv pip install dist/*.whl")
    print("2. Upload to PyPI: uv run python -m twine upload dist/*")
    print(
        "3. Or upload to TestPyPI: uv run python -m twine upload --repository testpypi dist/*"
    )
    print("4. Install in development: uv pip install -e .")


if __name__ == "__main__":
    main()
