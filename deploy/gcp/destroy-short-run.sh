#!/bin/bash
set -euo pipefail

usage() {
    echo "Použití: $0 --terraform-dir=DIR --var-file=FILE --archive-dir=DIR --confirm-destroy=DESTROY-SHORT-RUN"
}

terraform_dir=""
var_file=""
archive_dir=""
confirmation=""
for argument in "$@"; do
    case "$argument" in
        --terraform-dir=*) terraform_dir="${argument#--terraform-dir=}" ;;
        --var-file=*) var_file="${argument#--var-file=}" ;;
        --archive-dir=*) archive_dir="${argument#--archive-dir=}" ;;
        --confirm-destroy=*) confirmation="${argument#--confirm-destroy=}" ;;
        *) usage; exit 2 ;;
    esac
done
if [ -z "$terraform_dir" ] || [ -z "$var_file" ] || [ -z "$archive_dir" ] || [ "$confirmation" != "DESTROY-SHORT-RUN" ]; then
    usage
    exit 2
fi
if [ ! -d "$terraform_dir" ] || [ ! -f "$var_file" ] || [ ! -d "$archive_dir" ]; then
    echo "Chyba: Terraform adresář, var-file nebo lokální archivní adresář neexistuje." >&2
    exit 1
fi
terraform_dir=$(realpath "$terraform_dir")
var_file=$(realpath "$var_file")
archive_dir=$(realpath "$archive_dir")
if ! find "$archive_dir" -type f -name archive-report.json -print -quit | grep -q .; then
    echo "Chyba: v lokálním adresáři není ověřený event archiv. Nejprve spusťte archive a collect." >&2
    exit 1
fi

plan_file="$terraform_dir/short-run-destroy.tfplan"
terraform -chdir="$terraform_dir" plan -destroy -var-file="$var_file" -out="$plan_file"
terraform -chdir="$terraform_dir" apply "$plan_file"
echo "Short-run infrastruktura byla odstraněna. Lokální archivy zůstaly v $archive_dir."
