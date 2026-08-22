#!/bin/bash
set -euo pipefail

usage() {
    echo "Použití: $0 --project=ID --zone=ZONE --vm=NAME --image=REGION-docker.pkg.dev/...@sha256:..."
}

project=""
zone=""
vm=""
image=""
for argument in "$@"; do
    case "$argument" in
        --project=*) project="${argument#--project=}" ;;
        --zone=*) zone="${argument#--zone=}" ;;
        --vm=*) vm="${argument#--vm=}" ;;
        --image=*) image="${argument#--image=}" ;;
        *) usage; exit 2 ;;
    esac
done

if [ -z "$project" ] || [ -z "$zone" ] || [ -z "$vm" ] || [ -z "$image" ]; then
    usage
    exit 2
fi
if [[ ! "$image" =~ @sha256:[a-f0-9]{64}$ ]]; then
    echo "Chyba: deploy vyžaduje neměnný image digest, nikoli pouze tag." >&2
    exit 2
fi

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)
remote_path=/tmp/escape-bot-remote-deploy.sh

gcloud compute scp \
    --project="$project" --zone="$zone" --tunnel-through-iap \
    "$script_dir/remote-deploy.sh" "$vm:$remote_path"
gcloud compute ssh \
    --project="$project" --zone="$zone" --tunnel-through-iap \
    "$vm" --command="sudo bash $remote_path '$image'"

echo "Kontroluji veřejný endpoint podle konfigurace na VM..."
gcloud compute ssh \
    --project="$project" --zone="$zone" --tunnel-through-iap \
    "$vm" --command="sudo docker exec escape-bot-app python -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/health', timeout=3); urllib.request.urlopen('http://127.0.0.1:8080/api/ready', timeout=3)\""
