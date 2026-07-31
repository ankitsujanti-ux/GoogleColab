@echo off
REM Start the Flask backend (API + notification preview). Keep this window open.
REM In a SECOND terminal run: cd frontend && npm start
echo Starting Medication Adherence Dashboard backend...
echo.
echo After backend code changes (agent.py, app_flask.py, pharmacy.py), restart this script.
echo.
python main.py
pause
