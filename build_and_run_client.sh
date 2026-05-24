#!/bin/bash
#
# Skript pro spuštění webového klienta (nová architektura).
#
set -e

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &> /dev/null && pwd)
CLIENT_DIR="$SCRIPT_DIR/client"

cd "$CLIENT_DIR"

echo "OBSOLETE: Tento skript už není potřeba."
echo "Webový klient je nyní automaticky servírován přímo z centrálního backendu!"
echo "Pro spuštění hry použijte: ./start_backend.sh"
