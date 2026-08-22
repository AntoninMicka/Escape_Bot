#!/bin/bash
set -euo pipefail

if [ "$#" -ne 2 ]; then
    echo "Použití: $0 PROJECT ADMIN_SECRET" >&2
    exit 2
fi
project="$1"
admin_secret="$2"

if gcloud secrets versions access latest --project="$project" --secret="$admin_secret" >/dev/null 2>&1; then
    echo "Admin token již existuje; ponechávám současnou verzi."
else
    admin_token=$(openssl rand -hex 32)
    printf '%s' "$admin_token" | gcloud secrets versions add "$admin_secret" \
        --project="$project" --data-file=- >/dev/null
    unset admin_token
    echo "Vytvořena první verze admin tokenu."
fi
