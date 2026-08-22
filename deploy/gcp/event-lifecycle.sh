#!/bin/bash
set -euo pipefail

usage() {
    echo "Použití: $0 --project=ID --zone=ZONE --vm=NAME --action=archive|reset [--label=TEXT]"
}

project=""
zone=""
vm=""
action=""
label="event"
for argument in "$@"; do
    case "$argument" in
        --project=*) project="${argument#--project=}" ;;
        --zone=*) zone="${argument#--zone=}" ;;
        --vm=*) vm="${argument#--vm=}" ;;
        --action=*) action="${argument#--action=}" ;;
        --label=*) label="${argument#--label=}" ;;
        *) usage; exit 2 ;;
    esac
done
if [ -z "$project" ] || [ -z "$zone" ] || [ -z "$vm" ] || { [ "$action" != "archive" ] && [ "$action" != "reset" ]; }; then
    usage
    exit 2
fi
if [[ ! "$label" =~ ^[a-zA-Z0-9_-]{1,40}$ ]]; then
    echo "Chyba: label smí obsahovat pouze písmena, číslice, _ a -." >&2
    exit 2
fi

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)
remote_path=/tmp/escape-bot-event-lifecycle.sh
gcloud compute scp --project="$project" --zone="$zone" --tunnel-through-iap \
    "$script_dir/remote-event-lifecycle.sh" "$vm:$remote_path"
gcloud compute ssh --project="$project" --zone="$zone" --tunnel-through-iap \
    "$vm" --command="sudo bash $remote_path '$action' '$label'"
