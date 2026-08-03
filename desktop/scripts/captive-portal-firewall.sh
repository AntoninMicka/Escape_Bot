#!/bin/sh
set -eu

ACTION=${1:-}
INTERFACE=${2:-}

case "$INTERFACE" in
    ''|*[!A-Za-z0-9_.:-]*)
        echo "Neplatné síťové rozhraní." >&2
        exit 2
        ;;
esac

if ! command -v nft >/dev/null 2>&1; then
    echo "Chybí nftables." >&2
    exit 3
fi

disable_portal() {
    nft list table inet escapebot_captive >/dev/null 2>&1 \
        && nft delete table inet escapebot_captive \
        || true
}

case "$ACTION" in
    enable)
        disable_portal
        nft add table inet escapebot_captive
        nft 'add chain inet escapebot_captive prerouting { type nat hook prerouting priority dstnat; policy accept; }'
        nft add rule inet escapebot_captive prerouting iifname "$INTERFACE" udp dport 53 redirect to :5353
        nft add rule inet escapebot_captive prerouting iifname "$INTERFACE" tcp dport 53 redirect to :5353
        nft add rule inet escapebot_captive prerouting iifname "$INTERFACE" tcp dport 80 redirect to :8091
        ;;
    disable)
        disable_portal
        ;;
    *)
        echo "Použití: $0 enable|disable ROZHRANÍ" >&2
        exit 2
        ;;
esac

