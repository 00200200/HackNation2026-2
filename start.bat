@echo off
setlocal
pushd "%~dp0" || exit /b 1
if not "%~2"=="" goto usage
if "%~1"=="" (
    python -m kio2json
) else if /i "%~1"=="gui" (
    python -m kio2json.gui
) else (
    goto usage
)
set "result=%errorlevel%"
popd
exit /b %result%

:usage
echo Usage: start.bat [gui] 1>&2
popd
exit /b 2
