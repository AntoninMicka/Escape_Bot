#!/bin/bash
#
# Spouštěcí skript pro backend server.
#
# Tento skript automaticky:
# 1. Vytvoří virtuální prostředí (.venv), pokud neexistuje.
# 2. Nainstaluje závislosti z requirements.txt.
# 3. Spustí WebSocket server.
#
set -e # Ukončí skript při první chybě

# Přejdeme do adresáře backendu relativně k umístění skriptu
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &> /dev/null && pwd)
cd "$SCRIPT_DIR/backend"

# Zkontrolujeme, zda je nainstalován python3 a modul venv
if ! command -v python3 &> /dev/null || ! python3 -m venv -h &> /dev/null; then
    echo "Chyba: Python 3 a/nebo modul 'venv' nejsou k dispozici."
    echo "Nainstalujte prosím Python 3 a zkuste to znovu."
    exit 1
fi

# Zpracování argumentů
for argument in "$@"; do
    case "$argument" in
        --reset-venv)
            echo "Resetuji virtuální prostředí (mažu složku .venv)..."
            rm -rf .venv
            ;;
        --demo)
            export ESCAPEBOT_DEMO_MODE=1
            ;;
        *)
            echo "Neznámý parametr: $argument"
            echo "Použití: ./start_backend.sh [--demo] [--reset-venv]"
            exit 2
            ;;
    esac
done

# Vytvoření virtuálního prostředí, pokud neexistuje
if [ ! -d ".venv" ]; then
    echo "Vytvářím virtuální prostředí..."
    python3 -m venv .venv
fi

# Aktivace prostředí a instalace závislostí
echo "Aktivuji virtuální prostředí a instaluji závislosti..."
source .venv/bin/activate
pip install -r requirements.txt

echo "====================================================================="
echo "  Hra je připravena! Webový klient: https://localhost:8088  "
echo "  (Nebo zadejte http://localhost:8087 pro aut. přesměrování)"
if [ "${ESCAPEBOT_DEMO_MODE:-0}" = "1" ]; then
    echo "  DEMO REŽIM: https://localhost:8088/?demo=1"
fi
echo "====================================================================="

# Spuštění serveru
echo "Spouštím centrální uzel (na portu 8088)..."
python3 -m escape_bot.server
