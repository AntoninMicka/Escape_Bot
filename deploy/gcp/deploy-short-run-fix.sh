#!/bin/bash
set -euo pipefail

if [ "$#" -ne 9 ]; then
    echo "Použití: $0 PROJECT REGION ZONE VM BUCKET ENVIRONMENT VAR_FILE IMAGE_OR_EMPTY PROJECT_ROOT" >&2
    exit 2
fi
project="$1"; region="$2"; zone="$3"; vm="$4"; bucket="$5"; environment="$6"; var_file="$7"; image="$8"; root="$9"
if [ -z "$image" ]; then
    image=$("$root/deploy/gcp/build-short-run-image.sh" "$project" "$region")
fi
"$root/deploy/gcp/deploy.sh" --project="$project" --zone="$zone" --vm="$vm" --image="$image"
sed -i -E "s|^initial_image[[:space:]]*=.*$|initial_image = \"$image\"|" "$var_file"
gcloud storage cp "$var_file" "gs://$bucket/escape-bot/operator-config/$environment.tfvars" >/dev/null
"$root/deploy/gcp/lifecycle-state.sh" update "$project" "$bucket" "$environment" deployed_fix >/dev/null
printf 'Nasazen digest: %s\n' "$image"
