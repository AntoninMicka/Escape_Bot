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

host_architecture=$(uname -m)
if [ "$host_architecture" != "x86_64" ] && [ "$host_architecture" != "amd64" ]; then
    if ! { [ -r /proc/sys/fs/binfmt_misc/qemu-x86_64 ] && \
           grep -q '^enabled$' /proc/sys/fs/binfmt_misc/qemu-x86_64; } && \
       ! { command -v update-binfmts >/dev/null 2>&1 && \
           update-binfmts --display qemu-x86_64 2>/dev/null | grep -q '^ *status = enabled$'; }; then
        missing+=(amd64-emulation)
    fi
fi

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
if [ "${ID:-}" != "ubuntu" ] && [ "${ID:-}" != "debian" ]; then
    echo "Automatická instalace podporuje pouze přímo Debian a Ubuntu, nikoli jejich forky (nalezeno: ${ID:-neznámé})." >&2
    exit 1
fi

contains_missing() {
    local wanted="$1"
    local item
    for item in "${missing[@]}"; do [ "$item" = "$wanted" ] && return 0; done
    return 1
}

export DEBIAN_FRONTEND=noninteractive
# Vadný zdroj z předchozího pokusu nesmí zablokovat apt-get update dříve,
# než jej instalátor stihne znovu vytvořit.
if contains_missing terraform; then
    rm -f /etc/apt/sources.list.d/hashicorp.list \
        /etc/apt/sources.list.d/hashicorp.sources
fi
apt-get update
apt-get install -y ca-certificates curl gnupg
install -m 0755 -d /etc/apt/keyrings /usr/share/keyrings

if contains_missing terraform; then
    codename="${UBUNTU_CODENAME:-${VERSION_CODENAME:-}}"
    if [ -z "$codename" ]; then echo "Nelze určit kódové jméno distribuce." >&2; exit 1; fi
    release_url="https://apt.releases.hashicorp.com/dists/$codename/Release"
    if ! curl -fsSL "$release_url" -o /dev/null; then
        echo "HashiCorp APT repozitář nepodporuje distribuci '$codename' ($release_url)." >&2
        exit 1
    fi
    architecture=$(dpkg --print-architecture)
    curl -fsSL https://apt.releases.hashicorp.com/gpg \
        -o /etc/apt/keyrings/hashicorp.asc
    chmod 0644 /etc/apt/keyrings/hashicorp.asc
    cat > /etc/apt/sources.list.d/hashicorp.sources <<EOF
Types: deb
URIs: https://apt.releases.hashicorp.com
Suites: $codename
Components: main
Architectures: $architecture
Signed-By: /etc/apt/keyrings/hashicorp.asc
EOF
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
emulation_package=""
contains_missing terraform && packages+=(terraform)
contains_missing gcloud && packages+=(google-cloud-cli)
contains_missing docker && packages+=(docker.io)
if contains_missing amd64-emulation; then
    if apt-cache show qemu-user-binfmt >/dev/null 2>&1; then
        emulation_package="qemu-user-binfmt"
        packages+=(qemu-user-binfmt binfmt-support)
    elif apt-cache show qemu-user-static >/dev/null 2>&1; then
        emulation_package="qemu-user-static"
        packages+=(qemu-user-static binfmt-support)
    else
        echo "Chyba: distribuce nenabízí qemu-user-binfmt ani qemu-user-static." >&2
        exit 1
    fi
fi
apt-get install -y "${packages[@]}"

if [ "$emulation_package" = "qemu-user-binfmt" ]; then
    systemctl restart systemd-binfmt
elif [ "$emulation_package" = "qemu-user-static" ]; then
    update-binfmts --enable qemu-x86_64
fi

if contains_missing docker; then
    systemctl enable --now docker
    if [ -n "${OPERATOR_USER:-}" ] && id "$OPERATOR_USER" >/dev/null 2>&1; then
        usermod -aG docker "$OPERATOR_USER"
        echo "Uživatel $OPERATOR_USER byl přidán do skupiny docker. Projeví se po odhlášení a přihlášení."
    fi
fi

echo "Instalace závislostí byla dokončena."
