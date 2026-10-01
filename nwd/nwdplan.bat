@echo off
rem Drag a <name>.cache folder onto this file, then give the area and elevations (mm).
setlocal
set "CACHE=%~1"
if "%~1"=="" set /p "CACHE=Cache folder: "
python "%~dp0nwdplan.py" "%CACHE%" info
echo.
set RECT=
set CUT=
set BOT=
set NAME=plan
set /p RECT=Area X1 Y1 X2 Y2 (four numbers, spaces between; Enter = whole model): 
set /p CUT=Cut elevation Z (Enter = no cut): 
set /p BOT=Bottom elevation Z (Enter = none): 
set /p NAME=Drawing name (Enter = plan): 
set ARGS=
if not "%RECT%"=="" set ARGS=--rect %RECT%
if not "%CUT%"=="" set ARGS=%ARGS% --cut %CUT%
if not "%BOT%"=="" set ARGS=%ARGS% --bottom %BOT%
python "%~dp0nwdplan.py" "%CACHE%" plan --name "%NAME%" %ARGS%
echo.
pause
