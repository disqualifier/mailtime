#!/bin/bash

# Windows-specific runner for WSL environments
# This script uses Windows Python to run the GUI application or build

# Try to find Windows Python
WINDOWS_PYTHON=""
for path in "/mnt/c/Python"*/python.exe "/mnt/c/Users/"*/AppData/Local/Programs/Python/Python*/python.exe; do
    if [ -f "$path" ]; then
        WINDOWS_PYTHON="$path"
        break
    fi
done

if [ -z "$WINDOWS_PYTHON" ]; then
    echo "Windows Python not found. Please ensure Python is installed on Windows."
    echo "Alternative: Use commands directly from Windows Command Prompt or PowerShell"
    exit 1
fi

# Function to build the application
build() {
    echo "Building mail time! application using Windows Python..."

    # Check if assets exist
    if [ ! -f "assets/icon.png" ]; then
        echo "Warning: assets/icon.png not found. Building without icon."
    fi

    echo "Using Windows Python: $WINDOWS_PYTHON"
    echo "Building for Windows..."

    "$WINDOWS_PYTHON" -m PyInstaller app.spec --clean --noconfirm

    if [ -f "dist/mailtime.exe" ]; then
        echo "✅ Build successful! Executable created: dist/mailtime.exe"
    else
        echo "❌ Build failed!"
        exit 1
    fi

    echo "All resources bundled inside executable"
}

# Function to install dependencies
install() {
    echo "Installing dependencies using Windows Python..."
    echo "Using Windows Python: $WINDOWS_PYTHON"

    "$WINDOWS_PYTHON" -m pip install -r requirements.txt
    echo "Installing PyInstaller for building executables..."
    "$WINDOWS_PYTHON" -m pip install pyinstaller
}

# Function to clean build files
clean() {
    echo "Cleaning build files..."
    rm -rf build/ dist/ *.spec __pycache__/
    echo "✅ Clean complete!"
}

# Handle command line arguments
if [ "$1" = "install" ]; then
    install
elif [ "$1" = "build" ]; then
    build
elif [ "$1" = "clean" ]; then
    clean
elif [ "$1" = "help" ] || [ "$1" = "--help" ] || [ "$1" = "-h" ]; then
    echo "Usage: ./run-windows.sh [command]"
    echo ""
    echo "Commands:"
    echo "  (no args)  Run the GUI application"
    echo "  install    Install dependencies and PyInstaller"
    echo "  build      Build Windows executable using PyInstaller"
    echo "  clean      Clean build files and cache"
    echo "  help       Show this help message"
    echo ""
    echo "This script uses Windows Python for full GUI support in WSL"
    echo "Build output: dist/mailtime.exe"
    exit 0
else
    # Default: run the application
    echo "Starting mail time! application using Windows Python..."
    echo "Using Windows Python: $WINDOWS_PYTHON"

    # Run the application with Windows Python
    "$WINDOWS_PYTHON" mailtime_app.py
fi