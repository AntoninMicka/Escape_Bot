@echo off
::
:: Dávka pro sestavení a spuštění QML klienta.
::
:: Tato dávka automaticky:
:: 1. Nakonfiguruje projekt pomocí CMake.
:: 2. Sestaví projekt.
:: 3. Spustí výslednou aplikaci.
::
setlocal

:: Zkontrolujeme, zda je k dispozici cmake
cmake --version >nul 2>nul
if %errorlevel% neq 0 (
    echo Chyba: 'cmake' neni nainstalovan nebo neni v ceste (PATH).
    echo Ujistete se, ze mate nainstalovane buildovaci nastroje (napr. Visual Studio) a CMake.
    pause
    exit /b 1
)

set "SCRIPT_DIR=%~dp0"
set "CLIENT_DIR=%SCRIPT_DIR%client"
set "BUILD_DIR=%CLIENT_DIR%\build"

cd /d "%CLIENT_DIR%"

echo Konfiguruji projekt v adresari 'build'...
cmake -S . -B "%BUILD_DIR%"
if %errorlevel% neq 0 (
    echo Chyba pri konfiguraci projektu pomoci CMake.
    pause
    exit /b 1
)

echo Sestavuji projekt...
cmake --build "%BUILD_DIR%"
if %errorlevel% neq 0 (
    echo Chyba pri sestavovani projektu.
    pause
    exit /b 1
)

:: Název spustitelného souboru podle targetu v client\CMakeLists.txt
set "EXECUTABLE_NAME=EscapeBotClient.exe"
set "EXECUTABLE_PATH=%BUILD_DIR%\%EXECUTABLE_NAME%"

:: Pro Visual Studio generátor může být cíl v podadresáři s konfigurací
if not exist "%EXECUTABLE_PATH%" ( set "EXECUTABLE_PATH=%BUILD_DIR%\Debug\%EXECUTABLE_NAME%" )
if not exist "%EXECUTABLE_PATH%" ( set "EXECUTABLE_PATH=%BUILD_DIR%\Release\%EXECUTABLE_NAME%" )

if exist "%EXECUTABLE_PATH%" (
    echo Spoustim klienta...
    start "" "%EXECUTABLE_PATH%"
) else (
    echo Varovani: Spustitelny soubor '%EXECUTABLE_NAME%' nebyl nalezen.
    echo Zkontrolujte adresar '%BUILD_DIR%' (a jeho podadresare Debug/Release).
    dir "%BUILD_DIR%"
    pause
)

endlocal
