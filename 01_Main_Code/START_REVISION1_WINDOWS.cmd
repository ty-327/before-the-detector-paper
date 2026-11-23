@echo off
setlocal
cd /d "%~dp0"
echo COSE Revision 1 scoped reviewer check - candidate
echo Python 3.12 is required. First use installs pinned packages.
py -3.12 --version >nul 2>nul
if not errorlevel 1 goto use_py
python "%~dp0run_revision1.py" --setup
goto done
:use_py
py -3.12 "%~dp0run_revision1.py" --setup
:done
set "COSE_REVISION1_EXIT=%errorlevel%"
echo.
echo Full manuscript reproduction remains NOT_ESTABLISHED.
if not "%COSE_REVISION1_EXIT%"=="0" echo Scoped checks did not complete. Read the reported error.
pause
exit /b %COSE_REVISION1_EXIT%
