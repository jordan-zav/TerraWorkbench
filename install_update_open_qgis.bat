@echo off
setlocal EnableExtensions

rem TerraWorkbench local installer and updater for the QGIS installation on this PC.
set "QGIS_ROOT=E:\QGIS"
set "PLUGIN_ID=TerraWorkbench"
set "PLUGIN_SOURCE=%~dp0."
set "PROFILES_ROOT=%APPDATA%\QGIS\QGIS3\profiles"
set "PROFILES_INI=%PROFILES_ROOT%\profiles.ini"
set "PROFILE_NAME=default"

if not exist "%QGIS_ROOT%\bin\qgis-ltr.bat" (
    echo ERROR: QGIS was not found at %QGIS_ROOT%.
    pause
    exit /b 1
)

if not exist "%PLUGIN_SOURCE%\metadata.txt" (
    echo ERROR: Run this BAT from the root of the TerraWorkbench project.
    pause
    exit /b 1
)

if exist "%PROFILES_INI%" (
    for /f "tokens=1,* delims==" %%A in ('findstr /B /I "lastProfile=" "%PROFILES_INI%"') do set "PROFILE_NAME=%%B"
)

if not exist "%PROFILES_ROOT%\%PROFILE_NAME%" (
    echo ERROR: The QGIS profile "%PROFILE_NAME%" does not exist.
    pause
    exit /b 1
)

tasklist /FI "IMAGENAME eq qgis-bin.exe" 2>NUL | find /I "qgis-bin.exe" >NUL
if not errorlevel 1 (
    echo ERROR: Close QGIS before installing or updating the plugin.
    pause
    exit /b 1
)

set "PLUGIN_DEST=%PROFILES_ROOT%\%PROFILE_NAME%\python\plugins\%PLUGIN_ID%"
set "PROFILE_SETTINGS=%PROFILES_ROOT%\%PROFILE_NAME%\QGIS\QGIS3.ini"
if not exist "%PLUGIN_DEST%" mkdir "%PLUGIN_DEST%"

echo.
echo [1/4] Installing or updating %PLUGIN_ID% in profile "%PROFILE_NAME%"...
robocopy "%PLUGIN_SOURCE%" "%PLUGIN_DEST%" /E /COPY:DAT /DCOPY:DAT /R:1 /W:1 /NFL /NDL /NJH /NJS /NP /XD .git __pycache__ tests /XF install_update_open_qgis.bat *.pyc
set "COPY_RESULT=%ERRORLEVEL%"
if %COPY_RESULT% GEQ 8 (
    echo ERROR: The plugin files could not be copied. Close QGIS and try again.
    pause
    exit /b %COPY_RESULT%
)

echo [2/4] Checking the scientific Python dependencies...
call "%QGIS_ROOT%\bin\python-qgis-ltr.bat" -m pip install --user --disable-pip-version-check -r "%PLUGIN_SOURCE%\requirements.txt"
if errorlevel 1 (
    echo ERROR: Python dependencies could not be installed.
    pause
    exit /b 1
)

echo [3/4] Enabling %PLUGIN_ID% in QGIS...
call "%QGIS_ROOT%\bin\python-qgis-ltr.bat" -c "from qgis.PyQt.QtCore import QSettings; s=QSettings(r'%PROFILE_SETTINGS%', QSettings.IniFormat); s.setValue('PythonPlugins/GeofisQ', False); s.setValue('PythonPlugins/%PLUGIN_ID%', True); s.sync(); raise SystemExit(0 if s.status() == QSettings.NoError else 1)"
if errorlevel 1 (
    echo ERROR: The plugin was copied, but could not be enabled in profile "%PROFILE_NAME%".
    pause
    exit /b 1
)

if /I "%~1"=="--no-launch" goto completed

echo [4/4] Opening QGIS with profile "%PROFILE_NAME%"...
call "%QGIS_ROOT%\bin\qgis-ltr.bat" --profile "%PROFILE_NAME%"

:completed
echo.
echo DONE: %PLUGIN_ID% is installed or updated at:
echo %PLUGIN_DEST%
endlocal
exit /b 0
