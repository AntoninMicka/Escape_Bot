#!/bin/bash
set -euo pipefail

usage() { echo "Použití: $0 --project=ID --state-bucket=BUCKET --workspace=NAME --terraform-dir=DIR --var-file=FILE"; }
project=""; state_bucket=""; workspace=""; terraform_dir=""; var_file=""
for argument in "$@"; do
    case "$argument" in
        --project=*) project="${argument#--project=}" ;;
        --state-bucket=*) state_bucket="${argument#--state-bucket=}" ;;
        --workspace=*) workspace="${argument#--workspace=}" ;;
        --terraform-dir=*) terraform_dir="${argument#--terraform-dir=}" ;;
        --var-file=*) var_file="${argument#--var-file=}" ;;
        *) usage; exit 2 ;;
    esac
done
if [ -z "$project" ] || [ -z "$state_bucket" ] || [ -z "$workspace" ] || [ -z "$terraform_dir" ] || [ -z "$var_file" ]; then
    usage; exit 2
fi
mkdir -p "$(dirname "$var_file")"
gcloud storage cp "gs://$state_bucket/escape-bot/operator-config/$workspace.tfvars" "$var_file" >&2
terraform -chdir="$terraform_dir" init -reconfigure \
    -backend-config="bucket=$state_bucket" -backend-config="prefix=escape-bot/short-run" >&2
terraform -chdir="$terraform_dir" workspace select "$workspace" >&2
terraform -chdir="$terraform_dir" output -json
