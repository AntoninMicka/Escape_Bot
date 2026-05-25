@echo off
::
:: Spouštěcí dávka pro backend server.
::
:: Tato dávka automaticky:
:: 1. Vytvoří virtuální prostředí (.venv), pokud neexistuje.
:: 2. Nainstaluje závislosti z requirements.txt.
:: 3. Spustí WebSocket server.
::
setlocal

:: Přejdeme do adresáře backendu relativně k umístění skriptu
cd /d "%~dp0\backend"

:: Zkontrolujeme, zda je k dispozici python
python --version >nul 2>nul
if %errorlevel% neq 0 (
    echo Chyba: Python neni nainstalovan nebo neni v ceste (PATH).
    echo Nainstalujte prosim Python 3 a zkuste to znovu.
    pause
    exit /b 1
)

:: Vytvoření virtuálního prostředí, pokud neexistuje
if not exist ".venv" (
    echo Vytvarim virtualni prostredi...
    python -m venv .venv
    if %errorlevel% neq 0 (
        echo Chyba pri vytvareni virtualniho prostredi.
        pause
        exit /b 1
    )
)

:: Aktivace prostředí a instalace závislostí
echo Aktivuji virtualni prostredi a instaluji zavislosti...
call .venv\Scripts\activate.bat
pip install -r requirements.txt

echo =====================================================================
echo   Hra je pripravena! Webovy klient: https://localhost:8088  
echo   (Nebo zadejte http://localhost:8087 pro aut. presmerovani)
echo =====================================================================

:: Spuštění serveru
echo Spoustim centralni uzel (na portu 8088)...
python -m escape_bot.server

endlocal