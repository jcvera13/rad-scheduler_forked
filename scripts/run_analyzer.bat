@echo off
REM Fair Radiology Schedule Analyzer - Windows Launcher
REM Double-click this file to run the analyzer

echo ========================================
echo Fair Radiology Schedule Analyzer
echo ========================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo.
    echo Please install Python from https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during installation
    echo.
    pause
    exit /b 1
)

echo Python found!
echo.

REM Check for required packages
echo Checking required packages...
python -c "import pandas" 2>nul
if errorlevel 1 (
    echo Installing pandas...
    pip install pandas
)

python -c "import openpyxl" 2>nul
if errorlevel 1 (
    echo Installing openpyxl...
    pip install openpyxl
)

python -c "import matplotlib" 2>nul
if errorlevel 1 (
    echo Installing matplotlib...
    pip install matplotlib
)

echo.
echo ========================================
echo Ready to analyze!
echo ========================================
echo.

REM Prompt for file path
set /p SCHEDULE_FILE="Enter path to your schedule file (or drag & drop file here): "

REM Remove quotes if present
set SCHEDULE_FILE=%SCHEDULE_FILE:"=%

REM Check if file exists
if not exist "%SCHEDULE_FILE%" (
    echo.
    echo ERROR: File not found: %SCHEDULE_FILE%
    echo.
    pause
    exit /b 1
)

echo.
echo Analyzing: %SCHEDULE_FILE%
echo.

REM Ask if user wants to filter by date
set /p USE_DATES="Filter by date range? (y/n): "

if /i "%USE_DATES%"=="y" (
    set /p START_DATE="Enter start date (YYYY-MM-DD): "
    set /p END_DATE="Enter end date (YYYY-MM-DD): "
    
    REM Create output directory with timestamp
    set OUTPUT_DIR=Analysis_%date:~-4,4%%date:~-10,2%%date:~-7,2%_%time:~0,2%%time:~3,2%
    set OUTPUT_DIR=%OUTPUT_DIR: =0%
    mkdir "%OUTPUT_DIR%" 2>nul
    
    python analyze_schedule.py "%SCHEDULE_FILE%" --start-date %START_DATE% --end-date %END_DATE% --output-dir "%OUTPUT_DIR%"
) else (
    REM Create output directory with timestamp
    set OUTPUT_DIR=Analysis_%date:~-4,4%%date:~-10,2%%date:~-7,2%_%time:~0,2%%time:~3,2%
    set OUTPUT_DIR=%OUTPUT_DIR: =0%
    mkdir "%OUTPUT_DIR%" 2>nul
    
    python analyze_schedule.py "%SCHEDULE_FILE%" --output-dir "%OUTPUT_DIR%"
)

echo.
echo ========================================
echo Analysis Complete!
echo ========================================
echo.
echo Results saved to: %OUTPUT_DIR%
echo.
echo Files generated:
echo   - fairness_report.txt (detailed report)
echo   - fairness_data.json (data file)
echo   - assignment_distribution.png (chart)
echo   - deviation_from_mean.png (chart)
echo   - assignment_timeline.png (timeline)
echo.

REM Ask if user wants to open results folder
set /p OPEN_FOLDER="Open results folder? (y/n): "
if /i "%OPEN_FOLDER%"=="y" (
    start "" "%OUTPUT_DIR%"
)

echo.
pause
