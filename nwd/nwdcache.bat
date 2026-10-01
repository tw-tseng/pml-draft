@echo off
rem Drag a Navisworks ASCII .fbx onto this file: builds <name>.cache next to it (once per FBX).
setlocal
set "FBX=%~1"
if "%~1"=="" set /p "FBX=FBX file: "
python "%~dp0nwdcache.py" "%FBX%" --stats
echo.
pause
