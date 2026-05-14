#!/bin/bash
#
# Skript pro sestavení a spuštění QML klienta.
#
# Tento skript automaticky:
# 1. Nakonfiguruje projekt pomocí CMake.
# 2. Sestaví projekt.
# 3. Spustí výslednou aplikaci.
#
set -e

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &> /dev/null && pwd)
CLIENT_DIR="$SCRIPT_DIR/client"
BUILD_DIR="$CLIENT_DIR/build"

# Zkontrolujeme, zda je nainstalován cmake a C++ kompilátor
if ! command -v cmake &> /dev/null || ! command -v g++ &> /dev/null && ! command -v clang++ &> /dev/null; then
    echo "Chyba: 'cmake' a/nebo C++ kompilátor (g++/clang++) nejsou k dispozici."
    echo "Nainstalujte prosím potřebné nástroje a zkuste to znovu."
    exit 1
fi

cd "$CLIENT_DIR"

echo "Konfiguruji projekt v adresáři 'build'..."
cmake -S . -B "$BUILD_DIR"

echo "Sestavuji projekt..."
cmake --build "$BUILD_DIR"

# Název spustitelného souboru podle targetu v client/CMakeLists.txt
EXECUTABLE_NAME="EscapeBotClient"

if [ -f "$BUILD_DIR/$EXECUTABLE_NAME" ]; then
    echo "Spouštím klienta..."
    "$BUILD_DIR/$EXECUTABLE_NAME"
else
    echo "Varování: Spustitelný soubor '$EXECUTABLE_NAME' nebyl nalezen v '$BUILD_DIR'."
    echo "Zkontrolujte název projektu v CMakeLists.txt a upravte tento skript."
    echo "Procházím obsah adresáře '$BUILD_DIR':"
    ls -l "$BUILD_DIR"
fi
