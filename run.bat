@echo off
chcp 65001 >nul

REM 切换到脚本所在目录
cd /d "%~dp0"

echo ========================================
echo   MediaSpider - Road Collapse Crawler
echo ========================================
echo.

REM Check Python installation
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found. Install Python 3.8+ from:
    echo https://www.python.org/downloads/
    echo Check "Add Python to PATH" during install
    pause
    exit /b 1
)

echo [INFO] Python found:
python --version
echo.

REM Create virtual environment if not exists
if not exist "venv" (
    echo [INSTALL] Creating virtual environment...
    python -m venv venv
)

echo [INSTALL] Activating virtual environment...
call venv\Scripts\activate.bat

echo.
echo [INSTALL] Installing dependencies...
pip install -q PyQt5 selenium playwright beautifulsoup4 lxml requests feedparser loguru thefuzz python-Levenshtein markdownify PyYAML tqdm

echo.
echo [INSTALL] Installing Playwright browser (first time only)...
playwright install chromium --quiet 2>nul

echo.
echo ========================================
echo [START] Launching application...
echo ========================================
python main.py

pause
