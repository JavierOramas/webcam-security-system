#!/usr/bin/env python3
"""Test script to verify GitHub Actions setup."""

import sys
import os
from pathlib import Path


def test_imports():
    """Test that all modules can be imported."""
    print("🧪 Testing imports...")

    try:
        sys.path.insert(0, str(Path(__file__).parent / "src"))
        from webcam_security import SecurityMonitor, Config
        from webcam_security.cli import app

        print("✅ All imports successful")
        return True
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False


def test_config():
    """Test configuration functionality."""
    print("\n🧪 Testing configuration...")

    try:
        from webcam_security.config import Config

        config = Config(
            bot_token="test_token", chat_id="test_chat", topic_id="test_topic"
        )

        assert config.is_configured()
        print("✅ Configuration test passed")
        return True
    except Exception as e:
        print(f"❌ Config test error: {e}")
        return False


def test_build():
    """Test package building."""
    print("\n🧪 Testing package build...")

    try:
        import subprocess

        result = subprocess.run(
            ["python", "-m", "build"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent,
        )

        if result.returncode == 0:
            print("✅ Package build successful")
            return True
        else:
            print(f"❌ Build failed: {result.stderr}")
            return False
    except Exception as e:
        print(f"❌ Build test error: {e}")
        return False


def main():
    """Run all tests."""
    print("🚀 Testing GitHub Actions setup...")

    tests = [
        test_imports,
        test_config,
        test_build,
    ]

    passed = 0
    total = len(tests)

    for test in tests:
        if test():
            passed += 1

    print(f"\n📊 Test Results: {passed}/{total} tests passed")

    if passed == total:
        print("🎉 All tests passed! Ready for GitHub Actions.")
        print("\n📋 Next steps:")
        print("1. Add PYPI_API_TOKEN to GitHub secrets")
        print("2. Push to GitHub")
        print("3. Go to Actions tab to see workflows run")
        return True
    else:
        print("❌ Some tests failed. Please fix issues before pushing.")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
