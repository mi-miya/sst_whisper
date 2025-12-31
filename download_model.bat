@echo off
setlocal

set "MODEL_URL=https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-medium.bin"
set "MODEL_DIR=%~dp0models"
set "MODEL_PATH=%MODEL_DIR%\ggml-medium.bin"

if not exist "%MODEL_DIR%" (
    echo [INFO] Creating models directory...
    mkdir "%MODEL_DIR%"
)

if exist "%MODEL_PATH%" (
    echo [INFO] Model already exists at: %MODEL_PATH%
    choice /M "Do you want to re-download it?"
    if errorlevel 2 goto :EOF
)

echo [INFO] Downloading ggml-medium.bin...
echo [INFO] URL: %MODEL_URL%
echo.

curl -L -o "%MODEL_PATH%" "%MODEL_URL%"

if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Download failed. Please check your internet connection.
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo [SUCCESS] Model downloaded successfully.
pause
