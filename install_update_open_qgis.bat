@echo off
setlocal EnableExtensions

rem TerraWorkbench local installer and updater for a detected QGIS installation.
set "QGIS_ROOT_OVERRIDE=%QGIS_ROOT%"
set "QGIS_ROOT="
set "PLUGIN_ID=TerraWorkbench"
set "PLUGIN_SOURCE=%~dp0."
set "PROFILES_ROOT=%APPDATA%\QGIS\QGIS3\profiles"
set "PROFILES_INI=%PROFILES_ROOT%\profiles.ini"
set "PROFILE_NAME=default"

for /f "usebackq delims=" %%Q in (`powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\find_qgis.ps1" "%QGIS_ROOT_OVERRIDE%"`) do set "QGIS_ROOT=%%Q"
if not defined QGIS_ROOT (
    echo ERROR: A compatible QGIS installation was not found.
    echo Set QGIS_ROOT to the desired installation directory and retry.
    pause
    exit /b 1
)

set "QGIS_PYTHON=%QGIS_ROOT%\bin\python-qgis-ltr.bat"
if not exist "%QGIS_PYTHON%" set "QGIS_PYTHON=%QGIS_ROOT%\bin\python-qgis.bat"
set "QGIS_LAUNCHER=%QGIS_ROOT%\bin\qgis-ltr.bat"
if not exist "%QGIS_LAUNCHER%" set "QGIS_LAUNCHER=%QGIS_ROOT%\bin\qgis.bat"

echo Using QGIS at: %QGIS_ROOT%

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

for /f "delims=" %%V in ('call "%QGIS_PYTHON%" "%PLUGIN_SOURCE%\scripts\qgis_python_version.py"') do set "QGIS_PYTHON_VERSION=%%V"
if not defined QGIS_PYTHON_VERSION (
    echo ERROR: The QGIS Python version could not be detected.
    pause
    exit /b 1
)
set "DEPENDENCY_DIR=%PROFILES_ROOT%\%PROFILE_NAME%\python\dependencies\%PLUGIN_ID%\%QGIS_PYTHON_VERSION%"

if /I "%~1"=="--check" (
    echo.
    echo OK: QGIS and profile "%PROFILE_NAME%" are ready.
    echo QGIS: %QGIS_ROOT%
    echo Profile: %PROFILES_ROOT%\%PROFILE_NAME%
    echo Python: %QGIS_PYTHON_VERSION%
    echo Dependencies: %DEPENDENCY_DIR%
    endlocal
    exit /b 0
)

tasklist /FI "IMAGENAME eq qgis-bin.exe" 2>NUL | find /I "qgis-bin.exe" >NUL
if not errorlevel 1 (
    echo ERROR: Close QGIS before installing or updating the plugin.
    pause
    exit /b 1
)

set "PLUGIN_DEST=%PROFILES_ROOT%\%PROFILE_NAME%\python\plugins\%PLUGIN_ID%"
set "PROFILE_SETTINGS=%PROFILES_ROOT%\%PROFILE_NAME%\QGIS\QGIS3.ini"

rem A source-tree update must not retain removed modules or the legacy _vendor tree.
if exist "%PLUGIN_DEST%" rmdir /S /Q "%PLUGIN_DEST%"
if not exist "%PLUGIN_DEST%" mkdir "%PLUGIN_DEST%"

echo.
echo [1/4] Installing or updating %PLUGIN_ID% in profile "%PROFILE_NAME%"...
robocopy "%PLUGIN_SOURCE%" "%PLUGIN_DEST%" /E /COPY:DAT /DCOPY:DAT /R:1 /W:1 /NFL /NDL /NJH /NJS /NP /XD .git __pycache__ .pytest_cache tests dist scripts local_private /XF install_update_open_qgis.bat build_dist.bat *.pyc
set "COPY_RESULT=%ERRORLEVEL%"
if %COPY_RESULT% GEQ 8 (
    echo ERROR: The plugin files could not be copied. Close QGIS and try again.
    pause
    exit /b %COPY_RESULT%
)

echo [2/4] Checking the scientific Python dependencies...
if not exist "%DEPENDENCY_DIR%" mkdir "%DEPENDENCY_DIR%"
call "%QGIS_PYTHON%" -m pip install --disable-pip-version-check --upgrade --target "%DEPENDENCY_DIR%" -r "%PLUGIN_SOURCE%\requirements.txt"
if errorlevel 1 (
    echo ERROR: The 2D Python dependencies could not be installed.
    pause
    exit /b 1
)

call "%QGIS_PYTHON%" "%PLUGIN_SOURCE%\scripts\qgis_supports_inversion.py"
if not errorlevel 1 (
    call "%QGIS_PYTHON%" -m pip install --disable-pip-version-check --upgrade --target "%DEPENDENCY_DIR%" -r "%PLUGIN_SOURCE%\requirements-inversion.txt"
    if errorlevel 1 (
        echo ERROR: The optional 3D inversion dependencies could not be installed.
        pause
        exit /b 1
    )
) else (
    echo INFO: 3D inversion skipped because this QGIS uses Python older than 3.11.
)

echo [3/4] Enabling %PLUGIN_ID% in QGIS...
call "%QGIS_PYTHON%" -c "from qgis.PyQt.QtCore import QSettings; s=QSettings(r'%PROFILE_SETTINGS%', QSettings.IniFormat); s.setValue('PythonPlugins/GeofisQ', False); s.setValue('PythonPlugins/%PLUGIN_ID%', True); s.sync(); raise SystemExit(0 if s.status() == QSettings.NoError else 1)"
if errorlevel 1 (
    echo ERROR: The plugin was copied, but could not be enabled in profile "%PROFILE_NAME%".
    pause
    exit /b 1
)

if /I "%~1"=="--no-launch" goto completed

echo [4/4] Opening QGIS with profile "%PROFILE_NAME%"...
call "%QGIS_LAUNCHER%" --profile "%PROFILE_NAME%"

:completed
echo.
echo DONE: %PLUGIN_ID% is installed or updated at:
echo %PLUGIN_DEST%
endlocal
exit /b 0
