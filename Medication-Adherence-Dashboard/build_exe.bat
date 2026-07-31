@echo off
REM Build Medication Adherence Dashboard executable (production)
REM Run from project root. Output: dist\MedicationDashboard.exe
REM The exe runs on any Windows machine without Python installed.

setlocal
cd /d "%~dp0"

echo [1/4] Checking Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo Error: Python not found. Install Python 3.10+ and add to PATH.
    exit /b 1
)

echo [2/4] Checking frontend build...
if not exist "frontend\build\index.html" (
    echo Building React frontend...
    cd frontend
    call npm run build
    if errorlevel 1 ( echo Frontend build failed. & exit /b 1 )
    cd ..
) else (
    echo Frontend build found.
)

echo [3/4] Installing/updating PyInstaller...
pip install -q pyinstaller>=6.0.0
if errorlevel 1 ( echo pip install failed. & exit /b 1 )

echo [4/4] Building executable with PyInstaller...
python -m PyInstaller --noconfirm --clean MedicationDashboard.spec
if errorlevel 1 ( echo PyInstaller failed. & exit /b 1 )

echo Preparing dist folder...
if not exist "dist\Data" mkdir "dist\Data"
if exist ".env.example" copy /Y ".env.example" "dist\.env.example" >nul
if exist "DEPLOY.md" copy /Y "DEPLOY.md" "dist\DEPLOY.md" >nul

echo.
echo ========================================
echo   Build complete.
echo ========================================
echo   Executable: dist\MedicationDashboard.exe
echo.
echo   To run on ANY machine:
echo   1. Copy the "dist" folder (or just MedicationDashboard.exe + .env + Data) to the target PC.
echo   2. In that folder, copy .env.example to .env and set PORT, EXCEL_PATH, API keys.
echo   3. Put patients.xlsx in the Data folder (or set EXCEL_PATH in .env).
echo   4. Double-click MedicationDashboard.exe, then open http://localhost:5000
echo.
echo   See dist\DEPLOY.md for full instructions.
echo ========================================
endlocal
