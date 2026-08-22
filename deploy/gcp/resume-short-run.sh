#!/bin/bash
set -euo pipefail

if [ "$#" -ne 3 ] && [ "$#" -ne 4 ]; then
    echo "Použití: $0 PROJECT ZONE VM [SQL_INSTANCE]" >&2
    exit 2
fi

if [ "$#" -eq 4 ]; then
    gcloud sql instances patch "$4" --project="$1" --activation-policy=ALWAYS --quiet
fi
gcloud compute instances start "$3" --project="$1" --zone="$2"
echo "Short-run prostředí se spouští; před testem ověřte /api/ready."
