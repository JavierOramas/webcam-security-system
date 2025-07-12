#!/bin/bash
# Fast release script for webcam-security package using UV

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}🔄 $1${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

# Function to run commands with timing
run_command() {
    local cmd="$1"
    local description="$2"
    local start_time=$(date +%s.%N)
    
    print_status "$description"
    if eval "$cmd"; then
        local end_time=$(date +%s.%N)
        local elapsed=$(echo "$end_time - $start_time" | bc -l)
        print_success "$description completed (${elapsed}s)"
    else
        local end_time=$(date +%s.%N)
        local elapsed=$(echo "$end_time - $start_time" | bc -l)
        print_error "$description failed (${elapsed}s)"
        return 1
    fi
}

# Check if UV is installed
check_uv() {
    if ! command -v uv &> /dev/null; then
        print_warning "UV is not installed. Installing UV..."
        if curl -LsSf https://astral.sh/uv/install.sh | sh; then
            print_success "UV installed successfully"
            # Reload shell to get UV in PATH
            export PATH="$HOME/.cargo/bin:$PATH"
        else
            print_error "Failed to install UV. Please install manually: https://docs.astral.sh/uv/getting-started/installation/"
            exit 1
        fi
    fi
}

# Get current version
get_version() {
    grep 'version = "' pyproject.toml | sed 's/.*version = "\(.*\)"/\1/'
}

# Bump version
bump_version() {
    local bump_type="$1"
    print_status "Bumping $bump_type version"
    
    # Install bump2version if not available
    uv pip install bump2version
    
    local current_version=$(get_version)
    if [ -z "$current_version" ]; then
        print_error "Could not determine current version"
        exit 1
    fi
    IFS='.' read -r major minor patch <<< "$current_version"
    case "$bump_type" in
        "patch")
            patch=$((patch + 1))
            ;;
        "minor")
            minor=$((minor + 1))
            patch=0
            ;;
        "major")
            major=$((major + 1))
            minor=0
            patch=0
            ;;
        *)
            print_error "Invalid bump type: $bump_type. Use patch, minor, or major"
            exit 1
            ;;
    esac
    local new_version="$major.$minor.$patch"
    print_status "Bumping version: $current_version -> $new_version"
    uv run bump2version --current-version "$current_version" --new-version "$new_version" "$bump_type"
    print_success "Version bumped to $new_version"
}

# Build package
build_package() {
    print_status "Building package with UV"
    
    # Clean previous builds
    run_command "rm -rf build/ dist/ *.egg-info/ .pytest_cache/ .coverage htmlcov/" "Cleaning previous builds"
    
    # Install build dependencies
    run_command "uv pip install hatchling build twine" "Installing build dependencies"
    
    # Build wheel and source distribution in one command
    run_command "uv run python -m build" "Building package"
    
    # Check the built package
    run_command "uv run python -m twine check dist/*" "Checking package"
    
    print_success "Package built successfully"
}

# Upload to PyPI
upload_to_pypi() {
    local test_mode="$1"
    
    if [ "$test_mode" = "true" ]; then
        print_status "Uploading to TestPyPI"
        run_command "uv run python -m twine upload --repository testpypi dist/*" "Uploading to TestPyPI"
        print_success "Package uploaded to TestPyPI"
        echo "🔗 https://test.pypi.org/project/webcam-security/"
    else
        print_status "Uploading to PyPI"
        run_command "uv run python -m twine upload dist/*" "Uploading to PyPI"
        print_success "Package uploaded to PyPI"
        echo "🔗 https://pypi.org/project/webcam-security/"
    fi
}

# Create git tag
create_git_tag() {
    local version=$(get_version)
    print_status "Creating git tag v$version"
    
    run_command "git tag v$version" "Creating git tag"
    run_command "git push --tags" "Pushing git tags"
    
    print_success "Git tag v$version created and pushed"
}

# Test package
test_package() {
    print_status "Testing package installation"
    
    if build_package; then
        run_command "uv pip install dist/*.whl" "Testing package installation"
        print_success "Package test successful"
    else
        print_error "Build failed, cannot test"
        exit 1
    fi
}

# Show usage
show_usage() {
    echo "🚀 Webcam Security Release Script (UV-powered)"
    echo ""
    echo "Usage: $0 <command> [options]"
    echo ""
    echo "Commands:"
    echo "  build                    - Build package only"
    echo "  bump <patch|minor|major> - Bump version"
    echo "  upload [--test]          - Upload to PyPI (or TestPyPI with --test)"
    echo "  tag                      - Create and push git tag"
    echo "  full [--test]            - Full release (bump, build, upload, tag)"
    echo "  test                     - Test package installation"
    echo "  setup                    - Setup development environment"
    echo ""
    echo "Examples:"
    echo "  $0 build"
    echo "  $0 bump patch"
    echo "  $0 upload --test"
    echo "  $0 full --test"
    echo "  $0 setup"
}

# Main function
main() {
    if [ $# -eq 0 ]; then
        show_usage
        exit 1
    fi
    
    local command="$1"
    local test_mode="false"
    
    # Check for --test flag
    for arg in "$@"; do
        if [ "$arg" = "--test" ]; then
            test_mode="true"
        fi
    done
    
    echo "🚀 Webcam Security Release Script (UV-powered)"
    echo "📦 Command: $command"
    echo "🧪 Test mode: $test_mode"
    echo ""
    
    # Check UV installation
    check_uv
    
    case "$command" in
        "build")
            build_package
            ;;
        "bump")
            if [ -z "$2" ]; then
                print_error "Please specify version type: patch, minor, or major"
                exit 1
            fi
            bump_version "$2"
            ;;
        "upload")
            if build_package; then
                upload_to_pypi "$test_mode"
            else
                print_error "Build failed, cannot upload"
                exit 1
            fi
            ;;
        "tag")
            create_git_tag
            ;;
        "full")
            print_status "Starting full release process"
            
            # Determine bump type
            local bump_type="patch"
            if [ -n "$2" ] && [ "$2" != "--test" ]; then
                bump_type="$2"
            fi
            
            bump_version "$bump_type"
            build_package
            upload_to_pypi "$test_mode"
            create_git_tag
            
            local version=$(get_version)
            print_success "Full release completed successfully! Version: $version"
            ;;
        "test")
            test_package
            ;;
        "setup")
            print_status "Setting up development environment"
            
            # Create virtual environment
            run_command "uv venv" "Creating virtual environment"
            
            # Install package in development mode
            run_command "uv pip install -e ." "Installing package in development mode"
            
            # Install development dependencies
            if [ -f ".dev-requirements.txt" ]; then
                run_command "uv pip install -r .dev-requirements.txt" "Installing development dependencies"
            fi
            
            # Generate lock file
            run_command "uv lock" "Generating lock file"
            
            print_success "Development environment setup complete"
            echo ""
            echo "📋 Available commands:"
            echo "1. Activate environment: source .venv/bin/activate"
            echo "2. Run tests: uv run pytest"
            echo "3. Format code: uv run black src/ tests/"
            echo "4. Lint code: uv run ruff check src/ tests/"
            echo "5. Type check: uv run mypy src/"
            echo "6. Build package: $0 build"
            ;;
        *)
            print_error "Unknown command: $command"
            show_usage
            exit 1
            ;;
    esac
}

# Run main function with all arguments
main "$@" 