#!/bin/bash
set -euo pipefail

if [ "$#" -ne 3 ]; then
    echo "Použití: $0 PROJECT REGION BUCKET" >&2
    exit 2
fi
project="$1"; region="$2"; bucket="$3"
if [[ ! "$bucket" =~ ^[a-z0-9][a-z0-9._-]{1,61}[a-z0-9]$ ]]; then
    echo "Chyba: neplatný název GCS bucketu." >&2
    exit 2
fi

gcloud services enable storage.googleapis.com --project="$project"
if ! gcloud storage buckets describe "gs://$bucket" --project="$project" >/dev/null 2>&1; then
    gcloud storage buckets create "gs://$bucket" --project="$project" --location="$region" \
        --uniform-bucket-level-access --public-access-prevention
fi
gcloud storage buckets update "gs://$bucket" --project="$project" \
    --versioning --uniform-bucket-level-access --public-access-prevention
echo "Vzdálený Terraform state je připraven v gs://$bucket."
