#!/bin/bash
set -euo pipefail

image="${1:-}"
if [ -z "$image" ] || [[ ! "$image" =~ ^[a-z0-9.-]+-docker\.pkg\.dev/[a-z0-9:._/@-]+$ ]]; then
    echo "Chyba: očekávám úplný Artifact Registry image tag nebo digest." >&2
    exit 2
fi

deployment_dir=/opt/escape-bot
environment_file="$deployment_dir/.env"
compose_file="$deployment_dir/compose.yml"
if [ ! -f "$environment_file" ] || [ ! -f "$compose_file" ]; then
    echo "Chyba: VM bootstrap ještě není dokončen." >&2
    exit 1
fi

cd "$deployment_dir"
current_image=$(sed -n 's/^ESCAPEBOT_IMAGE=//p' "$environment_file")
backup_file=$(mktemp "$deployment_dir/.env.backup.XXXXXX")
cp "$environment_file" "$backup_file"
chmod 0600 "$backup_file"

restore_previous() {
    echo "Deploy selhal; vracím předchozí aplikační image." >&2
    cp "$backup_file" "$environment_file"
    docker compose --project-directory "$deployment_dir" -f "$compose_file" up -d --no-deps app || true
}
trap restore_previous ERR

docker pull "$image"
docker compose --project-directory "$deployment_dir" -f "$compose_file" up -d cloud-sql-proxy

docker run --rm \
    --network escape-bot-web \
    --env-file "$environment_file" \
    "$image" \
    python -m escape_bot.storage_migration --target postgres --schema-only

awk -v image="$image" '
    BEGIN { replaced = 0 }
    /^ESCAPEBOT_IMAGE=/ { print "ESCAPEBOT_IMAGE=" image; replaced = 1; next }
    { print }
    END { if (!replaced) print "ESCAPEBOT_IMAGE=" image }
' "$environment_file" > "$environment_file.new"
chmod 0600 "$environment_file.new"
mv "$environment_file.new" "$environment_file"

docker compose --project-directory "$deployment_dir" -f "$compose_file" up -d --no-deps app

ready=0
for attempt in $(seq 1 30); do
    if docker exec escape-bot-app python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/ready', timeout=3)" >/dev/null 2>&1; then
        ready=1
        break
    fi
    sleep 2
done
if [ "$ready" -ne 1 ]; then
    echo "Readiness nového kontejneru selhala." >&2
    exit 1
fi

docker compose --project-directory "$deployment_dir" -f "$compose_file" up -d caddy
rm -f "$backup_file"
trap - ERR
echo "Nasazen image: $image"
echo "Předchozí image: ${current_image:-žádný}"
