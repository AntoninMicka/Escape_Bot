#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)
CLOUDFLARE_DIR="$ROOT_DIR/cloudflare"
RUNTIME_BACKUP_DIR=""

usage() {
    cat <<'EOF'
Escape Bot – lokální vývoj, diagnostika a bezpečný deploy

Použití:
  ./run.sh doctor
  ./run.sh setup backend|cloudflare|all
  ./run.sh dev backend [argumenty start_backend.sh...]
  ./run.sh dev cloudflare [argumenty wrangler dev...]
  ./run.sh debug backend [argumenty start_backend.sh...]
  ./run.sh debug cloudflare [argumenty wrangler dev...]
  ./run.sh test backend|cloudflare|all
  ./run.sh check
  ./run.sh build cloudflare
  ./run.sh tail cloudflare staging|production [argumenty wrangler tail...]
  ./run.sh admin-token cloudflare staging|production [--yes]
  ./run.sh deploy cloudflare staging|production [--dry-run] [--yes]
  ./run.sh deploy gcp --project=ID --zone=ZONE --vm=NAME \
      --image=REGION-docker.pkg.dev/...@sha256:... [--dry-run] [--yes]

Poznámky:
  - `check` nic nenasazuje; sestaví a otestuje oba runtime.
  - Backendové testy automaticky obnoví sessions.json a lobbies.json.
  - `admin-token` načte tajnou hodnotu skrytě přímo přes Wrangler; nedávejte ji do argumentů.
  - Vzdálený deploy vyžaduje potvrzení; `--yes` je určený pro CI/automatizaci.
  - Produkční Cloudflare deploy navíc vyžaduje čistý pracovní strom.
EOF
}

fail() {
    echo "Chyba: $*" >&2
    exit 2
}

require_command() {
    command -v "$1" >/dev/null 2>&1 || fail "chybí příkaz '$1'."
}

require_cloudflare_dependencies() {
    require_command npm
    [ -d "$CLOUDFLARE_DIR/node_modules" ] || fail "chybí cloudflare/node_modules; spusťte './run.sh setup cloudflare'."
    export WRANGLER_LOG_PATH="${WRANGLER_LOG_PATH:-$CLOUDFLARE_DIR/.wrangler/logs}"
    mkdir -p -- "$WRANGLER_LOG_PATH"
}

require_clean_worktree() {
    if [ -n "$(git -C "$ROOT_DIR" status --porcelain)" ]; then
        echo "Produkční deploy byl zastaven: pracovní strom obsahuje změny." >&2
        git -C "$ROOT_DIR" status --short >&2
        exit 1
    fi
}

confirm_remote_action() {
    local label="$1"
    local assume_yes="$2"
    if [ "$assume_yes" -eq 1 ]; then
        return
    fi
    if [ ! -t 0 ]; then
        fail "vzdálená akce '$label' vyžaduje interaktivní potvrzení nebo --yes."
    fi
    echo "Chystá se vzdálená změna: $label" >&2
    read -r -p "Pro pokračování napište DEPLOY: " confirmation
    [ "$confirmation" = "DEPLOY" ] || fail "deploy zrušen."
}

cleanup_runtime_backup() {
    if [ -z "$RUNTIME_BACKUP_DIR" ] || [ ! -d "$RUNTIME_BACKUP_DIR" ]; then
        return
    fi
    local name
    for name in sessions.json lobbies.json; do
        if [ -f "$RUNTIME_BACKUP_DIR/$name" ]; then
            cp -- "$RUNTIME_BACKUP_DIR/$name" "$ROOT_DIR/backend/$name"
        elif [ -f "$RUNTIME_BACKUP_DIR/$name.missing" ]; then
            rm -f -- "$ROOT_DIR/backend/$name"
        fi
    done
    rm -rf -- "$RUNTIME_BACKUP_DIR"
    RUNTIME_BACKUP_DIR=""
}

backup_runtime_state() {
    cleanup_runtime_backup
    RUNTIME_BACKUP_DIR=$(mktemp -d "${TMPDIR:-/tmp}/escape-bot-tests.XXXXXX")
    local name
    for name in sessions.json lobbies.json; do
        if [ -f "$ROOT_DIR/backend/$name" ]; then
            cp -- "$ROOT_DIR/backend/$name" "$RUNTIME_BACKUP_DIR/$name"
        else
            touch "$RUNTIME_BACKUP_DIR/$name.missing"
        fi
    done
}

run_backend_tests() {
    require_command python3
    backup_runtime_state
    local status=0
    env PYTHONPATH="$ROOT_DIR/backend" python3 -m pytest -q "$ROOT_DIR/backend/tests" || status=$?
    cleanup_runtime_backup
    return "$status"
}

run_cloudflare_tests() {
    require_cloudflare_dependencies
    npm --prefix "$CLOUDFLARE_DIR" run check
}

setup_target() {
    case "${1:-}" in
        backend)
            require_command python3
            if [ ! -d "$ROOT_DIR/backend/.venv" ]; then
                python3 -m venv "$ROOT_DIR/backend/.venv"
            fi
            "$ROOT_DIR/backend/.venv/bin/python" -m pip install -r "$ROOT_DIR/backend/requirements.txt"
            ;;
        cloudflare)
            require_command npm
            npm --prefix "$ROOT_DIR/client/chronos-webgl" ci
            npm --prefix "$CLOUDFLARE_DIR" ci
            ;;
        all)
            setup_target backend
            setup_target cloudflare
            ;;
        *) fail "setup očekává backend, cloudflare nebo all." ;;
    esac
}

run_dev() {
    local target="${1:-}"
    shift || true
    case "$target" in
        backend) exec "$ROOT_DIR/start_backend.sh" "$@" ;;
        cloudflare)
            require_cloudflare_dependencies
            cd "$CLOUDFLARE_DIR"
            exec npm run dev -- "$@"
            ;;
        *) fail "dev očekává backend nebo cloudflare." ;;
    esac
}

run_debug() {
    local target="${1:-}"
    shift || true
    case "$target" in
        backend)
            export PYTHONASYNCIODEBUG=1
            export PYTHONFAULTHANDLER=1
            exec "$ROOT_DIR/start_backend.sh" --demo "$@"
            ;;
        cloudflare)
            export WRANGLER_LOG=debug
            run_dev cloudflare "$@"
            ;;
        *) fail "debug očekává backend nebo cloudflare." ;;
    esac
}

run_tests() {
    case "${1:-}" in
        backend) run_backend_tests ;;
        cloudflare) run_cloudflare_tests ;;
        all)
            run_backend_tests
            run_cloudflare_tests
            ;;
        *) fail "test očekává backend, cloudflare nebo all." ;;
    esac
}

set_cloudflare_admin_token() {
    local environment="${1:-}"
    shift || true
    case "$environment" in staging|production) ;; *) fail "admin-token očekává staging nebo production." ;; esac
    local assume_yes=0
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --yes) assume_yes=1 ;;
            *) fail "neznámý parametr nastavení admin tokenu: $1" ;;
        esac
        shift
    done
    require_cloudflare_dependencies
    if [ ! -t 0 ]; then
        fail "nastavení ADMIN_TOKEN vyžaduje interaktivní terminál. Token nepředávejte jako argument příkazu."
    fi
    confirm_remote_action "nastavení Cloudflare ADMIN_TOKEN pro $environment" "$assume_yes"
    cd "$CLOUDFLARE_DIR"
    exec npm exec wrangler secret put ADMIN_TOKEN -- --env "$environment"
}

deploy_cloudflare() {
    local environment="${1:-}"
    shift || true
    case "$environment" in staging|production) ;; *) fail "Cloudflare deploy očekává staging nebo production." ;; esac
    local dry_run=0 assume_yes=0
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --dry-run) dry_run=1 ;;
            --yes) assume_yes=1 ;;
            *) fail "neznámý parametr Cloudflare deploye: $1" ;;
        esac
        shift
    done
    require_cloudflare_dependencies
    if [ "$environment" = "production" ]; then
        require_clean_worktree
    fi
    cd "$CLOUDFLARE_DIR"
    npm run build
    npm run typecheck
    if [ "$dry_run" -eq 1 ]; then
        exec npm exec wrangler deploy -- --dry-run --env "$environment"
    fi
    confirm_remote_action "Cloudflare $environment" "$assume_yes"
    exec npm exec wrangler deploy -- --env "$environment"
}

deploy_gcp() {
    local dry_run=0 assume_yes=0
    local arguments=()
    local project="" zone="" vm="" image=""
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --dry-run) dry_run=1 ;;
            --yes) assume_yes=1 ;;
            --project=*) project="${1#--project=}"; arguments+=("$1") ;;
            --zone=*) zone="${1#--zone=}"; arguments+=("$1") ;;
            --vm=*) vm="${1#--vm=}"; arguments+=("$1") ;;
            --image=*) image="${1#--image=}"; arguments+=("$1") ;;
            *) fail "neznámý parametr GCP deploye: $1" ;;
        esac
        shift
    done
    [ -n "$project" ] && [ -n "$zone" ] && [ -n "$vm" ] && [ -n "$image" ] || \
        fail "GCP deploy vyžaduje --project, --zone, --vm a --image."
    [[ "$image" =~ @sha256:[a-f0-9]{64}$ ]] || fail "GCP deploy vyžaduje image s neměnným sha256 digestem."
    if [ "$dry_run" -eq 1 ]; then
        printf 'DRY-RUN: %q' "$ROOT_DIR/deploy/gcp/deploy.sh"
        printf ' %q' "${arguments[@]}"
        printf '\n'
        return
    fi
    require_command gcloud
    confirm_remote_action "GCP VM $vm v projektu $project ($zone), image $image" "$assume_yes"
    exec "$ROOT_DIR/deploy/gcp/deploy.sh" "${arguments[@]}"
}

doctor() {
    echo "Kořen projektu: $ROOT_DIR"
    local command_name
    for command_name in bash python3 npm git docker gcloud; do
        if command -v "$command_name" >/dev/null 2>&1; then
            printf '%-10s %s\n' "$command_name" "OK ($(command -v "$command_name"))"
        else
            printf '%-10s %s\n' "$command_name" "CHYBÍ"
        fi
    done
    [ -d "$ROOT_DIR/backend/.venv" ] && echo "backend venv: OK" || echo "backend venv: chybí (setup backend)"
    [ -d "$CLOUDFLARE_DIR/node_modules" ] && echo "Cloudflare dependencies: OK" || echo "Cloudflare dependencies: chybí (setup cloudflare)"
    git -C "$ROOT_DIR" status --short --branch
}

trap cleanup_runtime_backup EXIT
trap 'exit 130' INT TERM

command_name="${1:-help}"
shift || true
case "$command_name" in
    help|-h|--help) usage ;;
    doctor) [ "$#" -eq 0 ] || fail "doctor nepřijímá další argumenty."; doctor ;;
    setup) setup_target "${1:-}" ;;
    dev) run_dev "$@" ;;
    debug) run_debug "$@" ;;
    test) run_tests "${1:-}" ;;
    check)
        [ "$#" -eq 0 ] || fail "check nepřijímá další argumenty."
        run_backend_tests
        run_cloudflare_tests
        git -C "$ROOT_DIR" diff --check
        ;;
    build)
        [ "${1:-}" = "cloudflare" ] || fail "build aktuálně podporuje pouze cloudflare."
        require_cloudflare_dependencies
        exec npm --prefix "$CLOUDFLARE_DIR" run build
        ;;
    tail)
        [ "${1:-}" = "cloudflare" ] || fail "tail aktuálně podporuje pouze cloudflare."
        shift
        environment="${1:-}"
        shift || true
        case "$environment" in staging|production) ;; *) fail "tail očekává staging nebo production." ;; esac
        require_cloudflare_dependencies
        cd "$CLOUDFLARE_DIR"
        exec npm exec wrangler tail -- --env "$environment" "$@"
        ;;
    admin-token)
        [ "${1:-}" = "cloudflare" ] || fail "admin-token aktuálně podporuje pouze cloudflare."
        shift
        set_cloudflare_admin_token "$@"
        ;;
    deploy)
        target="${1:-}"
        shift || true
        case "$target" in
            cloudflare) deploy_cloudflare "$@" ;;
            gcp) deploy_gcp "$@" ;;
            *) fail "deploy očekává cloudflare nebo gcp." ;;
        esac
        ;;
    *) usage >&2; fail "neznámý příkaz '$command_name'." ;;
esac
