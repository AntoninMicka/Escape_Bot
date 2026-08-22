#!/bin/bash
set -euo pipefail

mode="${1:---check}"
if [ "$mode" != "--check" ] && [ "$mode" != "--install" ]; then
    echo "Použití: $0 [--check|--install]" >&2
    exit 2
fi

required=(gcloud terraform docker)
missing=()
for command_name in "${required[@]}"; do
    if ! command -v "$command_name" >/dev/null 2>&1; then
        missing+=("$command_name")
    fi
done

if [ "$mode" = "--check" ]; then
    if [ "${#missing[@]}" -ne 0 ]; then
        echo "Chybějící závislosti: ${missing[*]}" >&2
        echo "Použijte v Cloud Operatoru akci Zkontrolovat / nainstalovat závislosti." >&2
        exit 1
    fi
    gcloud --version | head -n 1
    terraform version | head -n 1
    docker --version
    if ! docker info >/dev/null 2>&1; then
        echo "Docker je nainstalovaný, ale služba neběží nebo k ní uživatel nemá oprávnění." >&2
        exit 1
    fi
    if [ -z "$(gcloud auth list --filter=status:ACTIVE --format='value(account)' 2>/dev/null)" ]; then
        echo "Google Cloud CLI není přihlášené. Použijte Přihlásit Google účet." >&2
        exit 1
    fi
    echo "Všechny závislosti jsou připravené."
    exit 0
fi

if [ "${#missing[@]}" -eq 0 ]; then
    echo "Všechny příkazy jsou již nainstalované."
    exec "$0" --check
fi

if [ "$(id -u)" -ne 0 ]; then
    if ! command -v pkexec >/dev/null 2>&1; then
        echo "Automatická instalace vyžaduje pkexec (balíček policykit-1)." >&2
        exit 1
    fi
    exec pkexec env OPERATOR_USER="${USER:-}" bash "$0" --install
fi

if [ ! -r /etc/os-release ]; then
    echo "Automatická instalace podporuje pouze Debian a Ubuntu." >&2
    exit 1
fi
. /etc/os-release
if [ "${ID:-}" != "ubuntu" ] && [ "${ID:-}" != "debian" ] && \
   [[ " ${ID_LIKE:-} " != *" debian "* ]]; then
    echo "Automatická instalace podporuje pouze Debian a Ubuntu (nalezeno: ${ID:-neznámé})." >&2
    exit 1
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y ca-certificates curl gnupg
install -m 0755 -d /usr/share/keyrings

contains_missing() {
    local wanted="$1"
    local item
    for item in "${missing[@]}"; do [ "$item" = "$wanted" ] && return 0; done
    return 1
}

if contains_missing terraform; then
    temporary_key=$(mktemp)
    curl -fsSL https://apt.releases.hashicorp.com/gpg -o "$temporary_key"
    gpg --batch --yes --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg "$temporary_key"
    rm -f "$temporary_key"
    codename="${UBUNTU_CODENAME:-${VERSION_CODENAME:-}}"
    if [ -z "$codename" ]; then echo "Nelze určit kódové jméno distribuce." >&2; exit 1; fi
    echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $codename main" \
        > /etc/apt/sources.list.d/hashicorp.list
fi

if contains_missing gcloud; then
    temporary_key=$(mktemp)
    curl -fsSL https://packages.cloud.google.com/apt/doc/apt-key.gpg -o "$temporary_key"
    gpg --batch --yes --dearmor -o /usr/share/keyrings/cloud.google.gpg "$temporary_key"
    rm -f "$temporary_key"
    echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" \
        > /etc/apt/sources.list.d/google-cloud-sdk.list
fi

apt-get update
packages=()
contains_missing terraform && packages+=(terraform)
contains_missing gcloud && packages+=(google-cloud-cli)
contains_missing docker && packages+=(docker.io)
apt-get install -y "${packages[@]}"

if contains_missing docker; then
    systemctl enable --now docker
    if [ -n "${OPERATOR_USER:-}" ] && id "$OPERATOR_USER" >/dev/null 2>&1; then
        usermod -aG docker "$OPERATOR_USER"
        echo "Uživatel $OPERATOR_USER byl přidán do skupiny docker. Projeví se po odhlášení a přihlášení."
    fi
fi

echo "Instalace závislostí byla dokončena."
