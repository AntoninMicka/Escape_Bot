#!/bin/bash
set -euo pipefail

usage() {
    echo "Použití: $0 --project=ID --zone=ZONE --vm=NAME --instance=SQL --environment=NAME --terraform-dir=DIR --var-file=FILE --image=IMAGE@sha256:..."
}

project=""; zone=""; vm=""; instance=""; environment=""; terraform_dir=""; var_file=""; image=""
for argument in "$@"; do
    case "$argument" in
        --project=*) project="${argument#--project=}" ;;
        --zone=*) zone="${argument#--zone=}" ;;
        --vm=*) vm="${argument#--vm=}" ;;
        --instance=*) instance="${argument#--instance=}" ;;
        --environment=*) environment="${argument#--environment=}" ;;
        --terraform-dir=*) terraform_dir="${argument#--terraform-dir=}" ;;
        --var-file=*) var_file="${argument#--var-file=}" ;;
        --image=*) image="${argument#--image=}" ;;
        *) usage; exit 2 ;;
    esac
done
if [ -z "$project" ] || [ -z "$zone" ] || [ -z "$vm" ] || [ -z "$instance" ] || \
   [ -z "$environment" ] || [ -z "$terraform_dir" ] || [ -z "$var_file" ] || [ -z "$image" ]; then
    usage; exit 2
fi

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)
prefix="escape-bot-$environment"

"$script_dir/provision-short-run.sh" \
    --terraform-dir="$terraform_dir" --var-file="$var_file" --workspace="$environment"
"$script_dir/configure-secrets.sh" \
    --project="$project" --instance="$instance" \
    --admin-secret="$prefix-admin-token" --database-secret="$prefix-database-password"

gcloud compute instances reset "$vm" --project="$project" --zone="$zone"
echo "Čekám na načtení tajemství a dokončení bootstrapu VM..."
ready=0
for attempt in $(seq 1 36); do
    if gcloud compute ssh "$vm" --project="$project" --zone="$zone" --tunnel-through-iap \
        --command="sudo test -s /opt/escape-bot/.env && sudo grep -q '^ESCAPEBOT_ADMIN_TOKEN=.' /opt/escape-bot/.env" \
        >/dev/null 2>&1; then
        ready=1
        break
    fi
    sleep 10
done
if [ "$ready" -ne 1 ]; then
    echo "Chyba: VM po restartu nepřipravila aplikační konfiguraci." >&2
    exit 1
fi

"$script_dir/deploy.sh" --project="$project" --zone="$zone" --vm="$vm" --image="$image"
echo "Krátkodobé prostředí je připraveno. Hru spusťte v admin dashboardu."
