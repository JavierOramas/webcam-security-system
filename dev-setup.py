#!/usr/bin/env python3
"""Fast development setup script using UV."""

import subprocess
import sys
import os
import shutil
from pathlib import Path


def run_command(cmd, description):
    """Run a command and handle errors."""
    print(f"🔄 {description}...")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"❌ Error: {result.stderr}")
        return False

    print(f"✅ {description} completed")
    if result.stdout.strip():
        print(result.stdout)
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
    """Main setup function."""
    print("🚀 Setting up webcam-security development environment with UV...")

    if not check_uv_installed():
        return False

    # Create virtual environment with UV (much faster than venv)
    if not run_command("uv venv", "Creating virtual environment"):
        return False

    # Install dependencies with UV (uses lock file for speed)
    if not run_command("uv pip install -e .", "Installing package in development mode"):
        return False

    # Install development dependencies
    if not run_command(
        "uv pip install -r .dev-requirements.txt", "Installing development dependencies"
    ):
        return False

    # Generate lock file for reproducible builds
    if not run_command("uv lock", "Generating lock file"):
        return False

    # Install pre-commit hooks
    if not run_command("uv run pre-commit install", "Installing pre-commit hooks"):
        print("⚠️  Pre-commit installation failed, continuing...")

    print("\n🎉 Development environment setup complete!")
    print("\n📋 Available commands:")
    print("1. Activate environment: source .venv/bin/activate")
    print("2. Run tests: uv run pytest")
    print("3. Format code: uv run black src/ tests/")
    print("4. Lint code: uv run ruff check src/ tests/")
    print("5. Type check: uv run mypy src/")
    print("6. Build package: python build.py")
    print("7. Install package: uv pip install -e .")


if __name__ == "__main__":
    main()
