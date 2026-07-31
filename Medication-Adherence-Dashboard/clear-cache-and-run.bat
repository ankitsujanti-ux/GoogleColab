@echo off
REM Clear Python bytecode cache so the latest .py code is always used, then start the backend.
echo Clearing Python cache (__pycache__)...
for /d /r . %%d in (__pycache__) do @if exist "%%d" rd /s /q "%%d" 2>nul
del /s /q *.pyc 2>nul
echo.
echo Starting backend...
python main.py
pause
