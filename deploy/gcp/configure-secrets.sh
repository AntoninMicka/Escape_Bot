#!/bin/bash
set -euo pipefail

usage() {
    echo "Použití: $0 --project=ID --instance=SQL_INSTANCE --admin-secret=NAME --database-secret=NAME"
}

project=""
instance=""
admin_secret=""
database_secret=""
for argument in "$@"; do
    case "$argument" in
        --project=*) project="${argument#--project=}" ;;
        --instance=*) instance="${argument#--instance=}" ;;
        --admin-secret=*) admin_secret="${argument#--admin-secret=}" ;;
        --database-secret=*) database_secret="${argument#--database-secret=}" ;;
        *) usage; exit 2 ;;
    esac
done

if [ -z "$project" ] || [ -z "$instance" ] || [ -z "$admin_secret" ] || [ -z "$database_secret" ]; then
    usage
    exit 2
fi

gcloud config set project "$project" >/dev/null

if gcloud secrets versions access latest --secret="$admin_secret" >/dev/null 2>&1; then
    echo "Admin token již existuje; ponechávám současnou verzi."
else
    admin_token=$(openssl rand -hex 32)
    printf '%s' "$admin_token" | gcloud secrets versions add "$admin_secret" --data-file=- >/dev/null
    unset admin_token
    echo "Vytvořena první verze admin tokenu."
fi

if gcloud secrets versions access latest --secret="$database_secret" >/dev/null 2>&1; then
    database_password=$(gcloud secrets versions access latest --secret="$database_secret")
    echo "Databázové heslo již existuje; použiji je pro synchronizaci uživatele."
else
    database_password=$(openssl rand -hex 32)
    printf '%s' "$database_password" | gcloud secrets versions add "$database_secret" --data-file=- >/dev/null
    echo "Vytvořena první verze databázového hesla."
fi

if gcloud sql users list --instance="$instance" --format='value(name)' | grep -qx 'escape_bot'; then
    gcloud sql users set-password escape_bot --instance="$instance" --password="$database_password" >/dev/null
else
    gcloud sql users create escape_bot --instance="$instance" --password="$database_password" >/dev/null
fi
unset database_password
echo "Tajemství a databázový uživatel jsou připraveni. Restartujte VM, pokud startup čekání již skončilo."
