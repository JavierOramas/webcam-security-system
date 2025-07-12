# Webcam Security

A Python package for webcam security monitoring with Telegram notifications. This package provides motion detection capabilities with configurable monitoring hours and automatic video recording.

## Features

- 🎥 Real-time motion detection using webcam
- 📱 Telegram notifications with snapshots
- ⏰ Configurable monitoring hours (default: 10 PM - 6 AM)
- 🎬 Automatic video recording on motion detection
- 🧹 Automatic cleanup of old recordings
- 🖥️ Live preview with monitoring status
- 🚀 Easy-to-use CLI interface

## Installation

```bash
pip install webcam-security
```

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

## Development

### Install in Development Mode

```bash
git clone <repository-url>
cd webcam-security
pip install -e .
```

### Run Tests

```bash
pip install -e ".[dev]"
pytest
```

## License

MIT License - see LICENSE file for details.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request. 