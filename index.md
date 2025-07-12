# Webcam Security

A Python package for webcam security monitoring with Telegram notifications. This package provides motion detection capabilities with configurable monitoring hours and automatic video recording.

## Features

- 🎥 Real-time motion detection using webcam
- 📱 Telegram notifications with snapshots
- ⏰ Configurable monitoring hours (default: 10 PM - 6 AM)
- 🎬 Automatic video recording on motion detection
- 🎵 Audio recording with video (combined MP4 format)
- 🧹 Automatic cleanup of old recordings
- 🖥️ Live preview with monitoring status
- 🚀 Easy-to-use CLI interface
- ⚡ UV-powered for faster builds and dependency management

## Installation

### Using pip (traditional)
```bash
pip install webcam-security
```

### Using UV (recommended - faster)
```bash
uv pip install webcam-security
```

## Quick Start

### 1. Initialize Configuration

First, set up your Telegram bot credentials:

```bash
webcam-security init --bot-token "YOUR_BOT_TOKEN" --chat-id "YOUR_CHAT_ID" --topic-id "OPTIONAL_TOPIC_ID"
```

### 2. Start Monitoring

```bash
webcam-security start
```

### 3. Stop Monitoring

```bash
webcam-security stop
```

## Configuration

### Required Parameters

- **Bot Token**: Your Telegram bot token from @BotFather
- **Chat ID**: The chat ID where notifications will be sent

### Configuration json:
This configuration file (`config.json`) contains all the settings required for the webcam-security system to function. Each field controls a specific aspect of how the monitoring and notifications work:

- **bot_token**: The Telegram bot token you get from @BotFather. This allows the system to send you notifications via Telegram.
- **chat_id**: The unique identifier for the Telegram chat (group, channel, or user) where alerts and recordings will be sent.
- **topic_id**: (Optional) If you are using a forum-style Telegram channel, this specifies the topic/thread for notifications.
- **monitoring_start_hour**: The hour (in 24-hour format) when monitoring should begin each day. Default is `22` (10 PM).
- **monitoring_end_hour**: The hour (in 24-hour format) when monitoring should stop each day. Default is `6` (6 AM).
- **grace_period**: The number of seconds to keep recording after motion is last detected. This helps capture the full event. Default is `25` seconds.
- **min_contour_area**: The minimum size (in pixels) of detected motion to trigger recording and notifications. Helps filter out small, irrelevant movements. Default is `500`.
- **motion_threshold**: The sensitivity of motion detection. Lower values make the system more sensitive to small changes. Default is `25`.
- **recording_fps**: Frames per second for the recorded video files. Default is `20.0`.
- **cleanup_days**: The number of days to keep old recordings before they are automatically deleted to save disk space. Default is `3`.

You can edit this file directly to fine-tune the system's behavior. The file is typically located at `~/.webcam_security/config.json` in your home directory. Make sure to keep your bot token private and do not share this file publicly.

### Optional Parameters

- **Topic ID**: For forum channels, specify the topic ID for organized notifications

## CLI Commands

### Initialize

```bash
webcam-security init --bot-token "YOUR_BOT_TOKEN" --chat-id "YOUR_CHAT_ID" [--topic-id "TOPIC_ID"]
```

### Start Monitoring

```bash
webcam-security start
```

### Stop Monitoring

```bash
webcam-security stop
```

### Help

```bash
webcam-security --help
webcam-security init --help
webcam-security start --help
webcam-security stop --help
```

## How It Works

1. **Motion Detection**: Uses OpenCV to detect motion in the webcam feed
2. **Monitoring Hours**: Only processes motion during configured hours (default: 10 PM - 6 AM)
3. **Notifications**: Sends Telegram messages with snapshots when motion is detected
4. **Recording**: Automatically records video during motion events
5. **Cleanup**: Removes old recordings to save disk space

## Requirements

- Python 3.8+
- Webcam access
- Internet connection for Telegram notifications
- OpenCV compatible camera
- FFmpeg (for audio/video merging)

## Development

### Fast Development Setup (Recommended)

This project uses **UV** for lightning-fast dependency management and builds.

#### 1. Quick Setup
```bash
git clone <repository-url>
cd webcam-security
make setup
```

#### 2. Alternative Manual Setup
```bash
# Install UV (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Setup development environment
python dev-setup.py
```

### Development Commands

#### Using Make (Fastest)
```bash
make help          # Show all available commands
make quick         # Format, lint, type-check, and test
make test          # Run tests with coverage
make build         # Build package
make release       # Full release process
```

#### Using UV Directly
```bash
uv run pytest      # Run tests
uv run black src/  # Format code
uv run ruff check  # Lint code
uv run mypy src/   # Type check
python build.py    # Build package
```

#### Using Release Scripts
```bash
# Python script
python release.py build
python release.py full --test

# Shell script
./release.sh build
./release.sh full --test
```

### Traditional Development (slower)

```bash
# Install in development mode
pip install -e .

# Install development dependencies
pip install -e ".[dev]"

# Run tests
pytest
```

## Performance Improvements

This project has been optimized for speed:

- **UV**: 10-100x faster than pip for dependency resolution
- **Hatchling**: Faster build backend than setuptools
- **Ruff**: 10-100x faster than flake8 for linting
- **Parallel processing**: Builds wheel and source distribution simultaneously
- **Caching**: UV caches dependencies for faster subsequent builds
- **Lock files**: Reproducible builds with `uv.lock`

## License

MIT License - see LICENSE file for details.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request. 