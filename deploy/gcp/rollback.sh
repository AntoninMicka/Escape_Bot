#!/bin/bash
set -euo pipefail

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)
echo "Rollback aplikace používá stejný ověřovaný deploy postup; databázové schéma automaticky nevrací."
exec "$script_dir/deploy.sh" "$@"
