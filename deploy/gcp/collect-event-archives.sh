#!/bin/bash
set -euo pipefail

if [ "$#" -ne 4 ]; then
    echo "Použití: $0 PROJECT ZONE VM LOCAL_DIRECTORY" >&2
    exit 2
fi
project="$1"
zone="$2"
vm="$3"
destination="$4"
mkdir -p "$destination"

gcloud compute scp --recurse --project="$project" --zone="$zone" --tunnel-through-iap \
    "$vm:/srv/escape-bot/data/event-archives" "$destination/"
echo "Archivy staženy do: $destination"
