@echo off
cd /d "%~dp0"
echo Pushing learning portal to GitHub...
echo If asked: username = ankitsujanti-ux
echo          password = your Personal Access Token (not your GitHub password)
echo.
git push -u origin main
if %ERRORLEVEL% EQU 0 (
    echo.
    echo Success! Wait 1 minute, then open:
    echo https://ankitsujanti-ux.github.io/GoogleColab/
) else (
    echo.
    echo Push failed. Create a token at:
    echo https://github.com/settings/tokens
    echo Scope: repo
)
pause
