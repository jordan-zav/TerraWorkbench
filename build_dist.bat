@echo off
setlocal EnableExtensions

set "PLUGIN_ID=TerraWorkbench"
set "PROJECT_ROOT=%~dp0."
set "DIST_DIR=%~dp0dist"

if not exist "%PROJECT_ROOT%\metadata.txt" (
    echo ERROR: Run this BAT from the TerraWorkbench project root.
    pause
    exit /b 1
)

for /f "tokens=1,* delims==" %%A in ('findstr /B /I "version=" "%PROJECT_ROOT%\metadata.txt"') do set "PLUGIN_VERSION=%%B"
if not defined PLUGIN_VERSION (
    echo ERROR: No version was found in metadata.txt.
    pause
    exit /b 1
)

if not exist "%DIST_DIR%" mkdir "%DIST_DIR%"
set "ZIP_PATH=%DIST_DIR%\%PLUGIN_ID%-%PLUGIN_VERSION%.zip"
if exist "%ZIP_PATH%" del /Q "%ZIP_PATH%"

echo Packaging %PLUGIN_ID% %PLUGIN_VERSION%...
tar.exe -a -c -f "%ZIP_PATH%" --exclude=dist --exclude=.git --exclude=__pycache__ --exclude=tests --exclude=*.pyc --exclude=0.7 --exclude=install_update_open_qgis.bat --exclude=build_dist.bat -C "%~dp0.." "%PLUGIN_ID%"
if errorlevel 1 (
    echo ERROR: The distribution ZIP could not be created.
    pause
    exit /b 1
)

echo DONE: %ZIP_PATH%
endlocal
exit /b 0
