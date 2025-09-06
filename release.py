#!/usr/bin/env python3
"""Comprehensive release script for webcam-security package."""

import subprocess
import sys
import os
import re
import time
from pathlib import Path
from typing import Tuple


def run(cmd, description):
    """Run a command and show output in real-time."""
    print(f"🔄 {description}...")
    start = time.time()

    try:
        result = subprocess.run(
            cmd,
            shell=True,
            check=True,
            capture_output=False,  # Show output in real-time
            text=True,
        )
        elapsed = time.time() - start
        print(f"✅ {description} completed ({elapsed:.2f}s)")
        return True
    except subprocess.CalledProcessError as e:
        elapsed = time.time() - start
        print(f"❌ {description} failed ({elapsed:.2f}s)")
        return False


def parse_version(version_string: str) -> Tuple[int, int, int]:
    """Parse version string into major, minor, patch components."""
    match = re.match(r'^(\d+)\.(\d+)\.(\d+)$', version_string)
    if not match:
        raise ValueError(f"Invalid version format: {version_string}")
    result = tuple(int(x) for x in match.groups())
    return (result[0], result[1], result[2])


def increment_version(version_string: str, increment_type: str = "patch") -> str:
    """Increment version string by the specified type."""
    major, minor, patch = parse_version(version_string)
    
    if increment_type == "major":
        major += 1
        minor = 0
        patch = 0
    elif increment_type == "minor":
        minor += 1
        patch = 0
    elif increment_type == "patch":
        patch += 1
    else:
        raise ValueError(f"Invalid increment type: {increment_type}")
    
    return f"{major}.{minor}.{patch}"


def update_file_version(file_path: Path, old_version: str, new_version: str) -> bool:
    """Update version in a file. Returns True if successful."""
    try:
        content = file_path.read_text(encoding='utf-8')
        
        # Update version in the file
        updated_content = content.replace(old_version, new_version)
        
        if updated_content != content:
            file_path.write_text(updated_content, encoding='utf-8')
            print(f"✅ Updated {file_path.name}: {old_version} → {new_version}")
            return True
        else:
            print(f"⚠️  No changes needed in {file_path.name}")
            return False
            
    except Exception as e:
        print(f"❌ Error updating {file_path.name}: {e}")
        return False


def get_current_version() -> str:
    """Get current version from pyproject.toml."""
    with open("pyproject.toml", "r") as f:
        content = f.read()
        match = re.search(r'version = "([^"]+)"', content)
        if match:
            return match.group(1)
    return ""


def update_version_files(increment_type: str = "patch") -> str:
    """Update version files and return the new version."""
    print("🔄 Updating version files...")
    
    current_version = get_current_version()
    if not current_version:
        print("❌ Could not determine current version")
        return ""
    
    # Calculate new version
    new_version = increment_version(current_version, increment_type)
    print(f"📈 Bumping version: {current_version} → {new_version}")
    
    # Files to update
    files_to_update = [
        Path("pyproject.toml"),
        Path("setup.py")
    ]
    
    # Update each file
    success_count = 0
    for file_path in files_to_update:
        if file_path.exists():
            if update_file_version(file_path, current_version, new_version):
                success_count += 1
        else:
            print(f"⚠️  File not found: {file_path.name}")
    
    if success_count == len(files_to_update):
        print(f"✅ Successfully updated version to {new_version}")
        return new_version
    else:
        print(f"❌ Some files could not be updated.")
        return ""


def bump_version(bump_type):
    """Bump version using bump2version."""
    current_version = get_current_version()
    if not current_version:
        print("❌ Could not determine current version")
        return False

    # Calculate new version
    major, minor, patch = map(int, current_version.split("."))
    if bump_type == "patch":
        patch += 1
    elif bump_type == "minor":
        minor += 1
        patch = 0
    elif bump_type == "major":
        major += 1
        minor = 0
        patch = 0
    else:
        print(f"❌ Unknown version type: {bump_type}")
        return False

    new_version = f"{major}.{minor}.{patch}"
    print(f"Bumping version: {current_version} -> {new_version}")

    # Install bump2version if needed
    if not run("pip install bump2version", "Installing bump2version"):
        return False

    # Bump version
    cmd = f"bump2version --current-version {current_version} --new-version {new_version} {bump_type}"
    return run(cmd, f"Bumping {bump_type} version")


def build_package():
    """Build the package."""
    # Clean and build
    if os.path.exists("dist"):
        import shutil

        shutil.rmtree("dist")

    if not run("pip install build", "Installing build tools"):
        return False

    if not run("python -m build", "Building package"):
        return False

    return True


def upload_to_pypi(test=False):
    """Upload to PyPI or TestPyPI."""
    if not run("pip install twine", "Installing twine"):
        return False

    if test:
        return run(
            "python -m twine upload dist/*",
            "Uploading to TestPyPI",
        )
    else:
        return run("python -m twine upload dist/*", "Uploading to PyPI")


def create_git_tag():
    """Create and push git tag."""
    version = get_current_version()
    if not version:
        print("❌ Could not determine version")
        return False

    if not run(f"git tag v{version}", f"Creating git tag v{version}"):
        return False

    if not run("git push --tags", "Pushing git tags"):
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
        print("  full [--test]            - Full release (update version, build, upload, tag)")
        print("  test                     - Test package installation")
        print("  update-version           - Update version files only")
        return

    command = sys.argv[1]
    test_mode = "--test" in sys.argv

    print("🚀 Webcam Security Release Script")
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
        print("\n🔄 Starting full release process...")

        # Determine bump type
        version_type = "patch"
        if len(sys.argv) >= 3 and sys.argv[2] in ["patch", "minor", "major"]:
            version_type = sys.argv[2]

        # NEW: Update version files first
        print(f"\n📝 Step 1: Updating version files ({version_type} increment)")
        new_version = update_version_files(version_type)
        if not new_version:
            print("\n❌ Version update failed!")
            sys.exit(1)

        # Continue with original full release process
        if not build_package():
            print("\n❌ Build failed!")
            sys.exit(1)

        if not upload_to_pypi(test_mode):
            print("\n❌ Upload failed!")
            sys.exit(1)

        if not create_git_tag():
            print("\n❌ Git tag creation failed!")
            sys.exit(1)

        print(f"\n🎉 Full release completed successfully! Version: {new_version}")

    elif command == "test":
        if build_package():
            print("\n🧪 Testing package installation...")
            if run("pip install dist/*.whl", "Testing package installation"):
                print("\n🎉 Package test successful!")
            else:
                print("\n❌ Package test failed!")
                sys.exit(1)
        else:
            print("\n❌ Build failed, cannot test!")
            sys.exit(1)

    elif command == "update-version":
        if len(sys.argv) < 3:
            print("❌ Please specify version type: patch, minor, or major")
            sys.exit(1)
        version_type = sys.argv[2]
        new_version = update_version_files(version_type)
        if new_version:
            print(f"\n🎉 Version updated to {new_version}")
        else:
            print("\n❌ Version update failed!")
            sys.exit(1)

    else:
        print(f"❌ Unknown command: {command}")


if __name__ == "__main__":
    main()
