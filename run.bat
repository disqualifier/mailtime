@echo off
setlocal

REM Function to find Python executable
set PYTHON=
for %%i in (python3.exe python.exe py.exe) do (
    where %%i >nul 2>&1
    if not errorlevel 1 (
        set PYTHON=%%i
        goto :found_python
    )
)

echo Python not found. Please install Python or ensure it's in your PATH.
pause
exit /b 1

:found_python

if "%1"=="install" (
    echo Installing dependencies...
    %PYTHON% -m pip install -r requirements.txt
    echo Installing PyInstaller for building executables...
    %PYTHON% -m pip install pyinstaller
    goto :end
)

if "%1"=="build" (
    echo Building executable with PyInstaller...

    REM Check if icon.png exists
    if not exist "assets\icon.png" (
        echo Warning: assets\icon.png not found. Building without icon.
    )

    echo Building for Windows...
    %PYTHON% -m PyInstaller app.spec --clean --noconfirm

    if exist "dist\mailtime.exe" (
        echo ✅ Build successful! Executable created: dist\mailtime.exe
    ) else (
        echo ❌ Build failed!
        pause
        exit /b 1
    )

    echo All resources bundled inside executable

    goto :end
)

if "%1"=="clean" (
    echo Cleaning build files...
    if exist "build" rmdir /s /q "build"
    if exist "dist" rmdir /s /q "dist"
    if exist "*.spec" del "*.spec"
    if exist "__pycache__" rmdir /s /q "__pycache__"
    echo ✅ Clean complete!
    goto :end
)

if "%1"=="help" (
    goto :help
)

if "%1"=="-h" (
    goto :help
)

if "%1"=="--help" (
    goto :help
)

if "%1"=="" (
    echo Starting mail time! application...
    %PYTHON% app.py
    goto :end
)

:help
echo Usage: run.bat [command]
echo.
echo Commands:
echo   (no args)  Run the application
echo   install    Install dependencies and PyInstaller
echo   build      Build executable using PyInstaller
echo   clean      Clean build files and cache
echo   help       Show this help message
echo.
echo Build output:
echo   Windows: dist\mailtime.exe

:end
if "%1"=="build" (
    pause
)