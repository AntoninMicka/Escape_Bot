#!/bin/bash
set -euo pipefail

action="${1:-}"
label="${2:-event}"
if [ "$action" != "archive" ] && [ "$action" != "reset" ]; then
    echo "Použití: $0 archive|reset LABEL" >&2
    exit 2
fi

deployment_dir=/opt/escape-bot
environment_file="$deployment_dir/.env"
compose_file="$deployment_dir/compose.yml"
image=$(sed -n 's/^ESCAPEBOT_IMAGE=//p' "$environment_file")
if [ -z "$image" ]; then
    echo "Chyba: chybí nasazený image." >&2
    exit 1
fi

mkdir -p /srv/escape-bot/data/event-archives
chown 10001:10001 /srv/escape-bot/data/event-archives

restart_app=1
# Archiv musí být konzistentní napříč všemi čtyřmi datovými sadami, proto
# po dobu exportu zastavíme zápisy i u pouhé závěrečné archivace.
docker compose --project-directory "$deployment_dir" -f "$compose_file" stop app

restart_after_failure() {
    if [ "$restart_app" -eq 1 ]; then
        docker compose --project-directory "$deployment_dir" -f "$compose_file" up -d app || true
    fi
}
trap restart_after_failure ERR

arguments=(
    python -m escape_bot.event_lifecycle
    --backend postgres
    --archive-root /exports/event-archives
    --label "$label"
)
if [ "$action" = "reset" ]; then
    arguments+=(--reset --confirm-reset RESET-EVENT-DATA)
fi

docker run --rm \
    --network escape-bot-web \
    --env-file "$environment_file" \
    -v /srv/escape-bot/data:/exports \
    "$image" "${arguments[@]}"

docker compose --project-directory "$deployment_dir" -f "$compose_file" up -d app
trap - ERR

echo "Archivy na VM: /srv/escape-bot/data/event-archives"
