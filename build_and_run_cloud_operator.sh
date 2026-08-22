#!/bin/bash
set -euo pipefail

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)
cmake -S "$script_dir/desktop" -B "$script_dir/desktop/build"
cmake --build "$script_dir/desktop/build" --target EscapeBotCloudOperator
exec "$script_dir/desktop/build/EscapeBotCloudOperator"
