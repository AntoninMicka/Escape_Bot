#!/bin/bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &> /dev/null && pwd)
BUILD_DIR="$SCRIPT_DIR/desktop/build"

for command_name in cmake c++; do
    if ! command -v "$command_name" &> /dev/null; then
        echo "Chyba: chybí nástroj $command_name."
        exit 1
    fi
done

if ! pkg-config --exists Qt6Core Qt6Network Qt6Widgets Qt6WebEngineWidgets; then
    echo "Chyba: chybí vývojové moduly Qt 6 včetně WebEngineWidgets."
    echo "Na Ubuntu/Debian nainstalujte zejména balíček qt6-webengine-dev."
    exit 1
fi

if ! command -v nmcli &> /dev/null; then
    echo "Upozornění: nmcli není dostupné; wrapper poběží, ale nevytvoří Wi-Fi AP."
fi

cmake -S "$SCRIPT_DIR/desktop" -B "$BUILD_DIR" -DCMAKE_BUILD_TYPE=Release
cmake --build "$BUILD_DIR" --parallel

exec "$BUILD_DIR/EscapeBotDesktop" "$@"

