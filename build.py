#!/usr/bin/env python3
"""Build script for webcam-security package."""

import subprocess
import sys
import os
from pathlib import Path


def run_command(cmd, description):
    """Run a command and handle errors."""
    print(f"🔄 {description}...")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"❌ Error: {result.stderr}")
        return False

    print(f"✅ {description} completed successfully")
    if result.stdout.strip():
        print(result.stdout)
    return True


def main():
    """Main build function."""
    print("🚀 Building webcam-security package...")

    # Clean previous builds
    if not run_command("rm -rf build/ dist/ *.egg-info/", "Cleaning previous builds"):
        return False

    # Install build dependencies
    if not run_command("pip install build twine", "Installing build dependencies"):
        return False

    # Build the package
    if not run_command("python -m build", "Building package"):
        return False

    # Check the built package
    if not run_command("python -m twine check dist/*", "Checking package"):
        return False

    print("\n🎉 Package built successfully!")
    print("\n📦 Built files:")
    for file in Path("dist").glob("*"):
        print(f"   {file}")

    print("\n📋 Next steps:")
    print("1. Test the package: pip install dist/*.whl")
    print("2. Upload to PyPI: python -m twine upload dist/*")
    print(
        "3. Or upload to TestPyPI: python -m twine upload --repository testpypi dist/*"
    )


if __name__ == "__main__":
    main()
