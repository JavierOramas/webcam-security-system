#!/bin/bash
# Simple wrapper for the Python release script

echo "🚀 Running Webcam Security Release Script..."
echo "============================================="

# Check if Python 3 is available
if command -v python3 &> /dev/null; then
    python3 release.py
elif command -v python &> /dev/null; then
    python release.py
else
    echo "❌ Error: Python not found. Please install Python 3."
    exit 1
fi 