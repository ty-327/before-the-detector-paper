@echo off
setlocal
cd /d "%~dp0"
echo COSE compact reviewer test
echo Python 3.12 is required. First use installs the pinned packages.
py -3.12 --version >nul 2>nul
if not errorlevel 1 goto use_py
python "%~dp0reviewer_test.py" --setup
goto done
:use_py
py -3.12 "%~dp0reviewer_test.py" --setup
:done
set "review_exit=%errorlevel%"
echo.
if not "%review_exit%"=="0" echo The reviewer test did not complete successfully. Read the error above.
pause
exit /b %review_exit%
