@echo off
REM Launch Luna Tpx3 GUI (Qt 6) from a terminal.
REM
REM Interpreter order:  %LUNA_PYTHON%  ->  .venv beside this script
REM                     ->  a venv under %USERPROFILE%\venvs  ->  py -3
REM
REM Uses python.exe on purpose, so a startup error stays readable in the
REM console. For a silent double-click launch with no console window, use the
REM Desktop shortcut instead -- see "Windows, way 2" in README.md.
setlocal
set "GUI=%~dp0src\main.py"

if defined LUNA_PYTHON if exist "%LUNA_PYTHON%" (
  "%LUNA_PYTHON%" "%GUI%" %*
  goto :done
)
if exist "%~dp0.venv\Scripts\python.exe" (
  "%~dp0.venv\Scripts\python.exe" "%GUI%" %*
  goto :done
)
if exist "%USERPROFILE%\venvs\tpx4cam\Scripts\python.exe" (
  "%USERPROFILE%\venvs\tpx4cam\Scripts\python.exe" "%GUI%" %*
  goto :done
)
py -3 "%GUI%" %*

:done
if errorlevel 1 pause
endlocal
