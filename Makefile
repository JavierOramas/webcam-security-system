# Makefile for webcam-security package (UV-powered)
.PHONY: help install dev test build clean lint format type-check release setup

# Default target
help:
	@echo "🚀 Webcam Security - Fast Development Commands"
	@echo "=============================================="
	@echo ""
	@echo "📦 Package Management:"
	@echo "  make setup      - Setup development environment with UV"
	@echo "  make install    - Install package in development mode"
	@echo "  make dev        - Install development dependencies"
	@echo ""
	@echo "🧪 Testing & Quality:"
	@echo "  make test       - Run tests with coverage"
	@echo "  make lint       - Run linting with ruff"
	@echo "  make format     - Format code with black"
	@echo "  make type-check - Run type checking with mypy"
	@echo ""
	@echo "🔨 Building & Release:"
	@echo "  make build      - Build package"
	@echo "  make clean      - Clean build artifacts"
	@echo "  make release    - Full release process"
	@echo ""
	@echo "⚡ Quick Commands:"
	@echo "  make quick      - Format, lint, type-check, and test"
	@echo "  make check      - Lint and type-check only"

# Setup development environment
setup:
	@echo "🔄 Setting up development environment..."
	@python dev-setup.py

# Install package in development mode
install:
	@echo "🔄 Installing package in development mode..."
	@uv pip install -e .

# Install development dependencies
dev:
	@echo "🔄 Installing development dependencies..."
	@uv pip install -r .dev-requirements.txt

# Run tests
test:
	@echo "🧪 Running tests..."
	@uv run pytest tests/ -v --cov=src/webcam_security --cov-report=term-missing

# Run linting
lint:
	@echo "🔍 Running linting..."
	@uv run ruff check src/ tests/

# Format code
format:
	@echo "🎨 Formatting code..."
	@uv run black src/ tests/

# Type checking
type-check:
	@echo "🔍 Running type checking..."
	@uv run mypy src/

# Build package
build:
	@echo "🔨 Building package..."
	@python build.py

# Clean build artifacts
clean:
	@echo "🧹 Cleaning build artifacts..."
	@rm -rf build/ dist/ *.egg-info/ .pytest_cache/ .coverage htmlcov/ .mypy_cache/

# Full release process
release:
	@echo "🚀 Starting release process..."
	@./release.sh full

# Quick development workflow
quick: format lint type-check test

# Quick check (no tests)
check: format lint type-check

# Install UV if not present
install-uv:
	@echo "🔄 Installing UV..."
	@curl -LsSf https://astral.sh/uv/install.sh | sh

# Update dependencies
update-deps:
	@echo "🔄 Updating dependencies..."
	@uv lock --upgrade

# Show package info
info:
	@echo "📦 Package Information:"
	@echo "Version: $(shell grep 'version = "' pyproject.toml | sed 's/.*version = "\(.*\)"/\1/')"
	@echo "Python: $(shell python --version)"
	@echo "UV: $(shell uv --version 2>/dev/null || echo 'Not installed')"

# Run security audit
audit:
	@echo "🔒 Running security audit..."
	@uv run safety check

# Generate documentation
docs:
	@echo "📚 Generating documentation..."
	@uv run pdoc --html src/webcam_security --output-dir docs

# Install pre-commit hooks
hooks:
	@echo "🔗 Installing pre-commit hooks..."
	@uv run pre-commit install

# Run pre-commit on all files
pre-commit:
	@echo "🔗 Running pre-commit on all files..."
	@uv run pre-commit run --all-files 