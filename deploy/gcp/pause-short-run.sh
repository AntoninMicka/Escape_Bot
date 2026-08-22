#!/bin/bash
set -euo pipefail

if [ "$#" -ne 4 ]; then
    echo "Použití: $0 PROJECT ZONE VM SQL_INSTANCE" >&2
    exit 2
fi

gcloud compute instances stop "$3" --project="$1" --zone="$2"
gcloud sql instances patch "$4" --project="$1" --activation-policy=NEVER --quiet
echo "Short-run prostředí je pozastavené; účtují se nadále disky, zálohy a rezervovaná IPv4."
