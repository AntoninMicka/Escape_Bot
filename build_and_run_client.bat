@echo off
::
:: Dávka pro spuštění webového klienta (nová architektura).
::
setlocal

cd /d "%~dp0\client"
echo OBSOLETE: Tento skript uz neni potreba.
echo Webovy klient je nyni automaticky servirovan primo z centralniho backendu!
echo Pro spusteni hry pouzijte: start_backend.bat
pause

endlocal
