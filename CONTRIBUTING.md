# Contributing to Webcam Security

Thank you for your interest in contributing to Webcam Security! This document provides guidelines and information for contributors.

## Development Setup

1. **Fork and clone the repository:**
   ```bash
   git clone https://github.com/yourusername/webcam-security.git
   cd webcam-security
   ```

2. **Install in development mode:**
   ```bash
   pip install -e ".[dev]"
   ```

3. **Install system dependencies:**
   - **Ubuntu/Debian:** `sudo apt-get install ffmpeg`
   - **macOS:** `brew install ffmpeg`
   - **Windows:** Download from [ffmpeg.org](https://ffmpeg.org/download.html)

## Development Workflow

### Making Changes

1. **Create a feature branch:**
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes** and test locally:
   ```bash
   # Test the CLI
   webcam-security --help
   
   # Test imports
   python -c "from webcam_security import SecurityMonitor, Config"
   ```

3. **Run tests locally:**
   ```bash
   # Linting
   flake8 src/
   
   # Type checking
   mypy src/ --ignore-missing-imports
   
   # Build package
   python -m build
   ```

4. **Commit your changes:**
   ```bash
   git add .
   git commit -m "feat: add your feature description"
   ```

### Version Bumping

To release a new version:

1. **Go to Actions tab** in GitHub
2. **Run "Bump Version" workflow**
3. **Choose bump type:**
   - `patch`: Bug fixes (0.1.0 → 0.1.1)
   - `minor`: New features (0.1.0 → 0.2.0)
   - `major`: Breaking changes (0.1.0 → 1.0.0)
4. **Review and merge the PR**
5. **Push to main** to trigger release

## Code Style

- **Python:** Follow PEP 8
- **Line length:** 88 characters (Black default)
- **Type hints:** Use type hints for all functions
- **Docstrings:** Use Google-style docstrings

## Testing

### Manual Testing

```bash
# Test configuration
webcam-security init --bot-token "test" --chat-id "test"

# Test status
webcam-security status

# Test monitoring (Ctrl+C to stop)
webcam-security start
```

### Automated Testing

The GitHub Actions will run:
- **Multi-platform testing** (Ubuntu, macOS, Windows)
- **Multi-version testing** (Python 3.8-3.12)
- **Security scanning** (Safety, Bandit)
- **Documentation generation**

## Release Process

1. **Version bump** (see above)
2. **Push to main** triggers:
   - Tests on all platforms
   - Package building
   - GitHub release creation
   - PyPI publication

## Issues and Pull Requests

### Reporting Issues

- Use the issue template
- Include system information
- Provide steps to reproduce
- Include error messages

### Pull Requests

- Reference related issues
- Include tests if applicable
- Update documentation
- Follow commit message conventions

## Commit Message Convention

Use conventional commits:
- `feat:` New features
- `fix:` Bug fixes
- `docs:` Documentation changes
- `style:` Code style changes
- `refactor:` Code refactoring
- `test:` Test changes
- `chore:` Maintenance tasks

## Security

- **Never commit secrets** (tokens, passwords)
- **Use environment variables** for sensitive data
- **Report security issues** privately to maintainers

## Questions?

Feel free to open an issue for questions or discussions! 