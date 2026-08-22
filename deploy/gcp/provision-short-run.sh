#!/bin/bash
set -euo pipefail

usage() { echo "Použití: $0 --terraform-dir=DIR --var-file=FILE --workspace=NAME"; }
terraform_dir=""
var_file=""
workspace=""
for argument in "$@"; do
    case "$argument" in
        --terraform-dir=*) terraform_dir="${argument#--terraform-dir=}" ;;
        --var-file=*) var_file="${argument#--var-file=}" ;;
        --workspace=*) workspace="${argument#--workspace=}" ;;
        *) usage; exit 2 ;;
    esac
done
if [ -z "$terraform_dir" ] || [ -z "$var_file" ] || [ -z "$workspace" ]; then usage; exit 2; fi
if [[ ! "$workspace" =~ ^[a-zA-Z0-9_-]{1,40}$ ]]; then
    echo "Chyba: neplatný název Terraform workspace." >&2; exit 2
fi
if [ ! -d "$terraform_dir" ] || [ ! -f "$var_file" ]; then
    echo "Chyba: Terraform adresář nebo var-file neexistuje." >&2; exit 1
fi
terraform_dir=$(realpath "$terraform_dir")
var_file=$(realpath "$var_file")
terraform -chdir="$terraform_dir" init
if ! terraform -chdir="$terraform_dir" workspace select "$workspace"; then
    terraform -chdir="$terraform_dir" workspace new "$workspace"
fi
plan_file="$terraform_dir/short-run-apply.tfplan"
terraform -chdir="$terraform_dir" plan -var-file="$var_file" -out="$plan_file"
terraform -chdir="$terraform_dir" apply "$plan_file"
