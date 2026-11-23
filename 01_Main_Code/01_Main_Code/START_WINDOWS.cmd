@echo off
setlocal
cd /d "%~dp0"
title COSE - Start reproduction
if not exist "%~dp0start_reproduction.py" goto missing_files
where py >nul 2>&1
if errorlevel 1 goto try_python
py -3.12 -c "import sys,struct; sys.exit(0 if sys.version_info[:2]==(3,12) and struct.calcsize('P')==8 else 1)" >nul 2>&1
if not errorlevel 1 goto run_py
:try_python
where python >nul 2>&1
if errorlevel 1 goto missing_python
python -c "import sys,struct; sys.exit(0 if sys.version_info[:2]==(3,12) and struct.calcsize('P')==8 else 1)" >nul 2>&1
if errorlevel 1 goto missing_python
goto run_python
:run_py
py -3.12 -u "%~dp0start_reproduction.py" %*
set "RC=%ERRORLEVEL%"
goto finish
:run_python
python -u "%~dp0start_reproduction.py" %*
set "RC=%ERRORLEVEL%"
goto finish
:missing_python
echo.
echo Install 64-bit Python 3.12 first, including pip and Tcl/Tk.
echo Then double-click START_WINDOWS.cmd again.
echo No analysis has been started.
set "RC=2"
goto finish
:missing_files
echo Extract ALL files from the repository ZIP before opening this launcher.
set "RC=2"
:finish
echo.
if "%RC%"=="0" echo Finished. Read the console messages above for the run status.
if not "%RC%"=="0" echo Stopped with code %RC%. Keep any logs and send them to Ty.
echo Press any key to close this window.
pause >nul
exit /b %RC%
