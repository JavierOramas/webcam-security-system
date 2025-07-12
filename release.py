#!/usr/bin/env python3
"""Release script for webcam-security package using UV."""

import subprocess
import sys
import os
import re
from pathlib import Path
import time


def run_command(cmd, description, check=True):
    """Run a command and handle errors."""
    print(f"🔄 {description}...")
    start_time = time.time()

    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

    elapsed = time.time() - start_time

    if result.returncode != 0:
        print(f"❌ Error ({elapsed:.2f}s): {result.stderr}")
        if check:
            return False
    else:
        print(f"✅ {description} completed ({elapsed:.2f}s)")
        if result.stdout.strip():
            print(result.stdout)

    return True


def get_current_version():
    """Get current version from pyproject.toml."""
    with open("pyproject.toml", "r") as f:
        content = f.read()
        match = re.search(r'version = "([^"]+)"', content)
        if match:
            return match.group(1)
    return None


def bump_version(version_type):
    """Bump version using UV and new bump2version CLI syntax."""
    current_version = get_current_version()
    if not current_version:
        print("❌ Could not determine current version")
        return False

    # Calculate new version
    major, minor, patch = map(int, current_version.split("."))
    if version_type == "patch":
        patch += 1
    elif version_type == "minor":
        minor += 1
        patch = 0
    elif version_type == "major":
        major += 1
        minor = 0
        patch = 0
    else:
        print(f"❌ Unknown version type: {version_type}")
        return False
    new_version = f"{major}.{minor}.{patch}"
    print(f"Bumping version: {current_version} -> {new_version}")
    return run_command(
        f"uv run bump2version --current-version {current_version} --new-version {new_version} {version_type}",
        f"Bumping {version_type} version to {new_version}",
    )


def build_package():
    """Build the package using UV."""
    # Clean previous builds
    if not run_command("rm -rf build/ dist/ *.egg-info/", "Cleaning previous builds"):
        return False

    # Install build dependencies with UV
    if not run_command(
        "uv pip install hatchling build twine bump2version",
        "Installing build dependencies",
    ):
        return False

    # Build wheel and source distribution in one command
    if not run_command("uv run python -m build", "Building package"):
        return False

    # Check the built package
    if not run_command("uv run python -m twine check dist/*", "Checking package"):
        return False

    return True


def upload_to_pypi(test=False):
    """Upload to PyPI or TestPyPI using UV."""
    if test:
        return run_command(
            "uv run python -m twine upload --repository testpypi dist/*",
            "Uploading to TestPyPI",
        )
    else:
        return run_command("uv run python -m twine upload dist/*", "Uploading to PyPI")


def create_git_tag():
    """Create and push git tag."""
    version = get_current_version()
    if not version:
        print("❌ Could not determine version")
        return False

    if not run_command(f"git tag v{version}", f"Creating git tag v{version}"):
        return False

    if not run_command("git push --tags", "Pushing git tags"):
        return False

    return True


def main():
    """Main release function."""
    if len(sys.argv) < 2:
        print("Usage: python release.py <command> [options]")
        print("\nCommands:")
        print("  build                    - Build package only")
        print("  bump <patch|minor|major> - Bump version")
        print("  upload [--test]          - Upload to PyPI (or TestPyPI with --test)")
        print("  tag                      - Create and push git tag")
        print("  full [--test]            - Full release (bump, build, upload, tag)")
        print("  test                     - Test package installation")
        return

    command = sys.argv[1]
    test_mode = "--test" in sys.argv

    print("🚀 Webcam Security Release Script (UV-powered)")
    print(f"📦 Command: {command}")
    print(f"🧪 Test mode: {test_mode}")

    if command == "build":
        if build_package():
            print("\n🎉 Package built successfully!")
        else:
            print("\n❌ Build failed!")
            sys.exit(1)

    elif command == "bump":
        if len(sys.argv) < 3:
            print("❌ Please specify version type: patch, minor, or major")
            sys.exit(1)
        version_type = sys.argv[2]
        if bump_version(version_type):
            new_version = get_current_version()
            print(f"\n🎉 Version bumped to {new_version}")
        else:
            print("\n❌ Version bump failed!")
            sys.exit(1)

    elif command == "upload":
        if build_package():
            if upload_to_pypi(test_mode):
                print("\n🎉 Upload successful!")
            else:
                print("\n❌ Upload failed!")
                sys.exit(1)
        else:
            print("\n❌ Build failed, cannot upload!")
            sys.exit(1)

    elif command == "tag":
        if create_git_tag():
            print("\n🎉 Git tag created and pushed!")
        else:
            print("\n❌ Git tag creation failed!")
            sys.exit(1)

    elif command == "full":
        # Full release process
        print("\n🔄 Starting full release process...")

        # Bump version
        if len(sys.argv) >= 3 and sys.argv[2] in ["patch", "minor", "major"]:
            version_type = sys.argv[2]
        else:
            version_type = "patch"

        if not bump_version(version_type):
            print("\n❌ Version bump failed!")
            sys.exit(1)

        # Build package
        if not build_package():
            print("\n❌ Build failed!")
            sys.exit(1)

        # Upload to PyPI
        if not upload_to_pypi(test_mode):
            print("\n❌ Upload failed!")
            sys.exit(1)

        # Create git tag
        if not create_git_tag():
            print("\n❌ Git tag creation failed!")
            sys.exit(1)

        new_version = get_current_version()
        print(f"\n🎉 Full release completed successfully! Version: {new_version}")

    elif command == "test":
        if build_package():
            print("\n🧪 Testing package installation...")
            if run_command("uv pip install dist/*.whl", "Testing package installation"):
                print("\n🎉 Package test successful!")
            else:
                print("\n❌ Package test failed!")
                sys.exit(1)
        else:
            print("\n❌ Build failed, cannot test!")
            sys.exit(1)

    else:
        print(f"❌ Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
