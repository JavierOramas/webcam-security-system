#!/usr/bin/env python3
"""Simple and fast build script for webcam-security package."""

import subprocess
import sys
import os
import shutil
from pathlib import Path
import time


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


def main():
    """Main build function."""
    print("🚀 Building webcam-security package...")

    # Clean previous builds
    if os.path.exists("dist"):
        shutil.rmtree("dist")
    if os.path.exists("build"):
        shutil.rmtree("build")
    for egg_info in Path(".").glob("*.egg-info"):
        shutil.rmtree(egg_info)

    print("✅ Cleaned previous builds")

    # Install build tools
    if not run("pip install build", "Installing build tools"):
        return False

    # Build package
    if not run("python -m build", "Building package"):
        return False

    # Check built files
    dist_files = list(Path("dist").glob("*"))
    if not dist_files:
        print("❌ No files found in dist/ directory")
        return False

    print(f"\n🎉 Package built successfully!")
    print(f"📦 Built {len(dist_files)} files:")
    for file in dist_files:
        size = file.stat().st_size / 1024  # KB
        print(f"   {file.name} ({size:.1f} KB)")

    print("\n📋 Next steps:")
    print("1. Test: pip install dist/*.whl")
    print("2. Upload: python -m twine upload dist/*")
    print("3. TestPyPI: python -m twine upload --repository testpypi dist/*")
    success = True

    return success


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
