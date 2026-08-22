#!/bin/bash
set -euo pipefail

usage() { echo "Použití: $0 --terraform-dir=DIR --var-file=FILE --workspace=NAME --state-bucket=BUCKET"; }
terraform_dir=""
var_file=""
workspace=""
state_bucket=""
for argument in "$@"; do
    case "$argument" in
        --terraform-dir=*) terraform_dir="${argument#--terraform-dir=}" ;;
        --var-file=*) var_file="${argument#--var-file=}" ;;
        --workspace=*) workspace="${argument#--workspace=}" ;;
        --state-bucket=*) state_bucket="${argument#--state-bucket=}" ;;
        *) usage; exit 2 ;;
    esac
done
if [ -z "$terraform_dir" ] || [ -z "$var_file" ] || [ -z "$workspace" ] || [ -z "$state_bucket" ]; then usage; exit 2; fi
if [[ ! "$workspace" =~ ^[a-zA-Z0-9_-]{1,40}$ ]]; then
    echo "Chyba: neplatný název Terraform workspace." >&2; exit 2
fi
if [ ! -d "$terraform_dir" ] || [ ! -f "$var_file" ]; then
    echo "Chyba: Terraform adresář nebo var-file neexistuje." >&2; exit 1
fi
if grep -Eiq '(^|[^a-z])(password|token|credential|private_key|secret)[[:space:]]*=' "$var_file"; then
    echo "Chyba: sdílený short-run tfvars nesmí obsahovat tajemství." >&2
    exit 1
fi
terraform_dir=$(realpath "$terraform_dir")
var_file=$(realpath "$var_file")
init_mode=(-reconfigure)
if [ -s "$terraform_dir/terraform.tfstate" ] || \
   find "$terraform_dir/terraform.tfstate.d" -type f -name terraform.tfstate -size +0c -print -quit 2>/dev/null | grep -q .; then
    echo "Nalezen lokální Terraform state; migruji jej do GCS."
    init_mode=(-migrate-state -force-copy)
fi
terraform -chdir="$terraform_dir" init "${init_mode[@]}" \
    -backend-config="bucket=$state_bucket" -backend-config="prefix=escape-bot/short-run"
if ! terraform -chdir="$terraform_dir" workspace select "$workspace"; then
    terraform -chdir="$terraform_dir" workspace new "$workspace"
fi
plan_file="$terraform_dir/short-run-apply.tfplan"
terraform -chdir="$terraform_dir" plan -var-file="$var_file" -var=enable_cloud_sql=false -out="$plan_file"
terraform -chdir="$terraform_dir" apply "$plan_file"
gcloud storage cp "$var_file" "gs://$state_bucket/escape-bot/operator-config/$workspace.tfvars"
