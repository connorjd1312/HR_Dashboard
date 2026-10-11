@echo off
rem Builds dist\HR_Analytics_Dashboard.exe — a single file you can double-click to run.
rem Run from this folder after setting up env\ (see CLAUDE.md).
cd /d "%~dp0"
call env\Scripts\activate || exit /b 1
pyinstaller HR_Analytics_Dashboard.spec --noconfirm --clean || exit /b 1
echo.
echo Built dist\HR_Analytics_Dashboard.exe
echo To use the AI Advisor without downloading again, copy the models folder next to the .exe.
