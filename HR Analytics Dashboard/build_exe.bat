@echo off
rem Double-click this file to build the HR Analytics Dashboard app and put it on
rem your desktop. The first run sets everything up (about 5-10 minutes); later
rem runs just rebuild the app (about 2 minutes). See README.md for help.
setlocal
cd /d "%~dp0"
set "INDEX=https://abetlen.github.io/llama-cpp-python/whl/cpu"

echo ============================================================
echo   HR Analytics Dashboard - build and add to desktop
echo ============================================================
echo.

rem ---- Step 1: one-time setup of the app's own Python environment ----
if exist "env\Scripts\python.exe" goto build

echo [1/3] First-time setup - this can take 5-10 minutes...
set "PY="
for %%V in (3.12 3.11 3.10 3.9) do (
    if not defined PY ( py -%%V -c "pass" >nul 2>&1 && set "PY=py -%%V" )
)
if not defined PY ( python -c "import sys; sys.exit(not (3, 9) <= sys.version_info[:2] <= (3, 12))" >nul 2>&1 && set "PY=python" )
if not defined PY (
    echo.
    echo  Python 3.9 - 3.12 was not found on this computer.
    echo  Install it from https://www.python.org/downloads/ - see README.md, step 1.
    goto failed
)
echo  Using %PY%
%PY% -m venv env || goto failed
rem The prebuilt AI library comes from INDEX, so no C++ compiler is needed
env\Scripts\python.exe -m pip install --upgrade pip || goto failed
env\Scripts\python.exe -m pip install -r requirements.txt --prefer-binary --extra-index-url %INDEX% || goto failed

:build
rem ---- Step 2: build the app ----
echo.
echo [2/3] Building the app - about 2 minutes...
rem Hide harmless library notices so the window only shows real problems
set "PYTHONWARNINGS=ignore"
env\Scripts\pyinstaller.exe HR_Analytics_Dashboard.spec --noconfirm --clean --log-level ERROR || goto failed

rem ---- Step 3: desktop shortcut ----
echo.
echo [3/3] Adding the app to your desktop...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$exe = (Resolve-Path 'dist\HR_Analytics_Dashboard.exe').Path;" ^
  "$lnk = Join-Path ([Environment]::GetFolderPath('Desktop')) 'HR Analytics Dashboard.lnk';" ^
  "$s = (New-Object -ComObject WScript.Shell).CreateShortcut($lnk);" ^
  "$s.TargetPath = $exe; $s.WorkingDirectory = Split-Path $exe; $s.IconLocation = $exe + ',0'; $s.Save()" || goto failed

echo.
echo ============================================================
echo   Done! Double-click "HR Analytics Dashboard" on your desktop.
echo ============================================================
echo.
pause
exit /b 0

:failed
echo.
echo ============================================================
echo   Something went wrong - see the messages above.
echo   README.md has a "If something goes wrong" section.
echo ============================================================
echo.
pause
exit /b 1
