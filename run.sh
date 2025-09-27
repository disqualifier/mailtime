#!/bin/bash

# Function to find Python executable
find_python() {
    # Try common Python commands in order of preference
    for python_cmd in python3 python py; do
        if command -v "$python_cmd" &> /dev/null; then
            echo "$python_cmd"
            return 0
        fi
    done

    # On Windows/WSL, try common installation paths
    if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" || -n "$WSL_DISTRO_NAME" ]]; then
        # Try Windows Python paths with wildcards
        for path in /mnt/c/Python*/python.exe /mnt/c/Users/*/AppData/Local/Programs/Python/Python*/python.exe; do
            if [ -f "$path" ]; then
                echo "$path"
                return 0
            fi
        done
    fi

    return 1
}

# Find Python executable
PYTHON=$(find_python)
if [ $? -ne 0 ]; then
    echo "Python not found. Please install Python or ensure it's in your PATH."
    exit 1
fi

if [ "$1" = "install" ]; then
    echo "Installing dependencies..."
    $PYTHON -m pip install -r requirements.txt
    echo "Installing PyInstaller for building executables..."
    $PYTHON -m pip install pyinstaller
elif [ "$1" = "build" ]; then
    echo "Building executable with PyInstaller..."

    # Check if icon.png exists
    if [ ! -f "assets/icon.png" ]; then
        echo "Warning: assets/icon.png not found. Building without icon."
    fi

    # Detect platform and build accordingly
    # Check if using Windows Python executable
    if [[ "$PYTHON" == *".exe" ]] || [[ "$OS" == "Windows_NT" ]] || [[ "$(uname -s)" == CYGWIN* ]] || [[ "$(uname -s)" == MINGW* ]] || [[ "$(uname -s)" == MSYS* ]]; then
        echo "Building for Windows..."
        $PYTHON -m PyInstaller app.spec --clean --noconfirm
        if [ -f "dist/mailtime.exe" ]; then
            echo "✅ Build successful! Executable created: dist/mailtime.exe"
        else
            echo "❌ Build failed!"
            exit 1
        fi
    else
        echo "Building for Linux/Mac..."
        $PYTHON -m PyInstaller app.spec --clean --noconfirm
        if [ -f "dist/mailtime" ]; then
            echo "✅ Build successful! Executable created: dist/mailtime"
        else
            echo "❌ Build failed!"
            exit 1
        fi
    fi

    # Files are now bundled inside the executable - no external copying needed
    echo "All resources bundled inside executable"

    exit 0
elif [ "$1" = "clean" ]; then
    echo "Cleaning build files..."
    rm -rf build/ dist/ *.spec __pycache__/
    echo "✅ Clean complete!"
    exit 0
elif [ "$1" = "help" ] || [ "$1" = "--help" ] || [ "$1" = "-h" ]; then
    echo "Usage: ./run.sh [command]"
    echo ""
    echo "Commands:"
    echo "  (no args)  Run the application"
    echo "  install    Install dependencies and PyInstaller"
    echo "  build      Build executable using PyInstaller"
    echo "  clean      Clean build files and cache"
    echo "  help       Show this help message"
    echo ""
    echo "For WSL GUI access:"
    echo "  ./run-windows.sh    Use Windows Python for GUI (recommended)"
    echo "  Or set up X11 forwarding for Linux GUI"
    echo ""
    echo "Build output:"
    echo "  Windows: dist/mailtime.exe"
    echo "  Linux/Mac: dist/mailtime"
    exit 0
fi

# Default action: run the application
echo "Starting mail time! application..."

# Handle WSL/headless display issues
if [[ -n "$WSL_DISTRO_NAME" ]] || [[ "$OSTYPE" == "linux-gnu" && -z "$DISPLAY" ]]; then
    echo "Detected WSL or headless Linux environment"
    echo "Setting QT_QPA_PLATFORM=offscreen for headless operation"
    export QT_QPA_PLATFORM=offscreen
    echo "Note: GUI will not be visible. This is for testing/headless operation only."
    echo "For GUI access, use Windows Python directly or set up X11 forwarding."
fi

$PYTHON app.py