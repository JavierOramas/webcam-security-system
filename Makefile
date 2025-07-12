# Makefile for webcam-security package (Simple & Fast)
.PHONY: help install dev test build clean lint format type-check release setup

# Default target
help:
	@echo "🚀 Webcam Security - Simple Development Commands"
	@echo "================================================"
	@echo ""
	@echo "📦 Package Management:"
	@echo "  make setup      - Setup development environment"
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
	@python -m venv .venv
	@echo "✅ Virtual environment created"
	@echo "📋 Next: source .venv/bin/activate && make install"

# Install package in development mode
install:
	@echo "🔄 Installing package in development mode..."
	@pip install -e .

# Install development dependencies
dev:
	@echo "🔄 Installing development dependencies..."
	@pip install -r .dev-requirements.txt

# Run tests
test:
	@echo "🧪 Running tests..."
	@pytest tests/ -v --cov=src/webcam_security --cov-report=term-missing

# Run linting
lint:
	@echo "🔍 Running linting..."
	@ruff check src/ tests/

# Format code
format:
	@echo "🎨 Formatting code..."
	@black src/ tests/

# Type checking
type-check:
	@echo "🔍 Running type checking..."
	@mypy src/

# Build package
build:
	@echo "🔨 Building package..."
	@python build_package.py

# Clean build artifacts
clean:
	@echo "🧹 Cleaning build artifacts..."
	@rm -rf build/ dist/ *.egg-info/ .pytest_cache/ .coverage htmlcov/ .mypy_cache/

# Full release process
release:
	@echo "🚀 Starting release process..."
	@python release.py full

# Quick development workflow
quick: format lint type-check test

# Quick check (no tests)
check: format lint type-check

# Update dependencies
update-deps:
	@echo "🔄 Updating dependencies..."
	@pip install --upgrade -r requirements.txt
	@pip install --upgrade -r .dev-requirements.txt

# Show package info
info:
	@echo "📦 Package Information:"
	@echo "Version: $(shell grep 'version = "' pyproject.toml | sed 's/.*version = "\(.*\)"/\1/')"
	@echo "Python: $(shell python --version)"

# Run security audit
audit:
	@echo "🔒 Running security audit..."
	@pip install safety
	@safety check

# Generate documentation
docs:
	@echo "📚 Generating documentation..."
	@pip install pdoc
	@pdoc --html src/webcam_security --output-dir docs

# Install pre-commit hooks
hooks:
	@echo "🔗 Installing pre-commit hooks..."
	@pip install pre-commit
	@pre-commit install

# Run pre-commit on all files
pre-commit:
	@echo "🔗 Running pre-commit on all files..."
	@pre-commit run --all-files 