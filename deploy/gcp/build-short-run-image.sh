#!/bin/bash
set -euo pipefail

if [ "$#" -ne 2 ]; then
    echo "Použití: $0 PROJECT REGION" >&2
    exit 2
fi
project="$1"; region="$2"
repository="$region-docker.pkg.dev/$project/escape-bot/app"
revision=$(git rev-parse --short=12 HEAD 2>/dev/null || echo source)
timestamp=$(date -u +%Y%m%d%H%M%S)
image="$repository:short-$revision-$timestamp"

gcloud auth configure-docker "$region-docker.pkg.dev" --quiet >&2
docker build --pull --label "org.opencontainers.image.revision=$revision" -t "$image" . >&2
docker push "$image" >&2
digest=$(docker inspect --format='{{index .RepoDigests 0}}' "$image")
if [[ ! "$digest" =~ @sha256:[a-f0-9]{64}$ ]]; then
    echo "Chyba: publikovaný image nemá platný digest." >&2
    exit 1
fi
printf '%s\n' "$digest"
