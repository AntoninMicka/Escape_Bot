#!/bin/bash
set -euo pipefail

usage() {
    echo "Použití: $0 --project=ID --region=REGION --zone=ZONE --vm=NAME --environment=NAME --state-bucket=BUCKET --terraform-dir=DIR --var-file=FILE [--image=IMAGE@sha256:...]"
}

project=""; region=""; zone=""; vm=""; environment=""; state_bucket=""; terraform_dir=""; var_file=""; image=""
for argument in "$@"; do
    case "$argument" in
        --project=*) project="${argument#--project=}" ;;
        --region=*) region="${argument#--region=}" ;;
        --zone=*) zone="${argument#--zone=}" ;;
        --vm=*) vm="${argument#--vm=}" ;;
        --environment=*) environment="${argument#--environment=}" ;;
        --state-bucket=*) state_bucket="${argument#--state-bucket=}" ;;
        --terraform-dir=*) terraform_dir="${argument#--terraform-dir=}" ;;
        --var-file=*) var_file="${argument#--var-file=}" ;;
        --image=*) image="${argument#--image=}" ;;
        *) usage; exit 2 ;;
    esac
done
if [ -z "$project" ] || [ -z "$region" ] || [ -z "$zone" ] || [ -z "$vm" ] || \
   [ -z "$environment" ] || [ -z "$state_bucket" ] || [ -z "$terraform_dir" ] || [ -z "$var_file" ]; then
    usage; exit 2
fi

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)
prefix="escape-bot-$environment"

"$script_dir/operator-dependencies.sh" --check

"$script_dir/bootstrap-state-bucket.sh" "$project" "$region" "$state_bucket"
"$script_dir/provision-short-run.sh" \
    --terraform-dir="$terraform_dir" --var-file="$var_file" --workspace="$environment" \
    --state-bucket="$state_bucket"
"$script_dir/configure-admin-secret.sh" "$project" "$prefix-admin-token"
if [ -z "$image" ]; then
    echo "Sestavuji první aplikační image..."
    image=$("$script_dir/build-short-run-image.sh" "$project" "$region")
fi
effective_domain=$(terraform -chdir="$terraform_dir" output -raw domain)
sed -i -E "s|^initial_image[[:space:]]*=.*$|initial_image = \"$image\"|" "$var_file"
sed -i -E "s|^domain[[:space:]]*=.*$|domain = \"$effective_domain\"|" "$var_file"
gcloud storage cp "$var_file" "gs://$state_bucket/escape-bot/operator-config/$environment.tfvars" >/dev/null

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
"$script_dir/lifecycle-state.sh" update "$project" "$state_bucket" "$environment" prepared_test >/dev/null
echo "Krátkodobé prostředí je připraveno. Hru spusťte v admin dashboardu."
