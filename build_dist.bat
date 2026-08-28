@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

echo ============================================================
echo   TerraWorkbench - QGIS release packager
echo ============================================================
echo.

where py.exe >nul 2>nul
if not errorlevel 1 (
    py.exe -3 scripts\package_plugin.py --interactive
    set "PACKAGE_RESULT=!ERRORLEVEL!"
    goto package_done
)

where python.exe >nul 2>nul
if errorlevel 1 (
    echo ERROR: Python 3 was not found in PATH.
    exit /b 1
)

python.exe scripts\package_plugin.py --interactive
set "PACKAGE_RESULT=%ERRORLEVEL%"

:package_done
if not "!PACKAGE_RESULT!"=="0" (
    echo.
    echo ERROR: The release package could not be created.
    exit /b !PACKAGE_RESULT!
)

echo.
echo DONE: The validated ZIP is available in dist.
endlocal
exit /b 0
