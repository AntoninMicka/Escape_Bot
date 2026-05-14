#!/bin/bash

# Zastaví skript při jakékoliv chybě
set -e

echo "=== Escape Bot: Sestavení klienta pro WebAssembly (WASM) ==="

# 1. Kontrola instalace Emscripten (emsdk)
if ! command -v emcc &> /dev/null
then
    echo "CHYBA: Příkaz 'emcc' (Emscripten) nebyl nalezen."
    echo "Nainstalujte emsdk a aktivujte jej:"
    echo "  git clone https://github.com/emscripten-core/emsdk.git"
    echo "  cd emsdk"
    echo "  ./emsdk install latest"
    echo "  ./emsdk activate latest"
    echo "  source ./emsdk_env.sh"
    exit 1
fi

# 2. Kontrola cesty k Qt pro WASM
# Pokud není nastavena proměnná QT_WASM_DIR, pokusíme se najít qt-cmake v PATH (nepravděpodobné, že je to ta wasm verze)
if [ -z "$QT_WASM_DIR" ]; then
    echo "CHYBA: Proměnná prostředí QT_WASM_DIR není nastavena."
    echo "Prosím nastavte ji tak, aby ukazovala na kořenovou složku Qt kompilovanou pro WebAssembly."
    echo "Příklad použití:"
    echo "  export QT_WASM_DIR=/opt/Qt/6.x.x/wasm_32"
    echo "  ./build_wasm.sh"
    exit 1
fi

QT_CMAKE="$QT_WASM_DIR/bin/qt-cmake"

if [ ! -f "$QT_CMAKE" ]; then
    echo "CHYBA: qt-cmake nebyl nalezen na cestě: $QT_CMAKE"
    echo "Zkontrolujte, zda je cesta v QT_WASM_DIR správná a zda obsahuje instalaci Qt pro WebAssembly."
    exit 1
fi

echo "Používám Emscripten: $(emcc --version | head -n 1)"
echo "Používám Qt CMake: $QT_CMAKE"

# 3. Příprava složky pro sestavení
BUILD_DIR="client/build-wasm"
mkdir -p "$BUILD_DIR"
cd "$BUILD_DIR"

echo "=== Konfigurace projektu (CMake) ==="
# Konfigurace projektu pomocí Qt wrapperu pro CMake (automaticky nastaví Emscripten toolchain)
"$QT_CMAKE" ..

echo "=== Kompilace ==="
cmake --build .

echo "=== Hotovo! ==="
echo "Webovou aplikaci můžete spustit spuštěním lokálního serveru ve složce $BUILD_DIR:"
echo "  cd $BUILD_DIR"
echo "  python3 -m http.server 8080"
echo "A otevřením adresy http://localhost:8080 v prohlížeči."
