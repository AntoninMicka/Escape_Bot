#!/bin/bash
set -euo pipefail

usage() {
    echo "Použití: $0 --project=ID --region=REGION [--version=vX.Y.Z]"
}

project=""
region=""
version=""
for argument in "$@"; do
    case "$argument" in
        --project=*) project="${argument#--project=}" ;;
        --region=*) region="${argument#--region=}" ;;
        --version=*) version="${argument#--version=}" ;;
        *) usage; exit 2 ;;
    esac
done
if [ -z "$project" ] || [ -z "$region" ]; then
    usage
    exit 2
fi
if ! git diff --quiet || ! git diff --cached --quiet; then
    echo "Chyba: release build vyžaduje čistý pracovní strom." >&2
    exit 1
fi

git_sha=$(git rev-parse --verify HEAD)
short_sha=$(git rev-parse --short=12 HEAD)
repository="$region-docker.pkg.dev/$project/escape-bot/app"
sha_image="$repository:git-$short_sha"

gcloud auth configure-docker "$region-docker.pkg.dev" --quiet
docker build --platform=linux/amd64 --pull --label "org.opencontainers.image.revision=$git_sha" -t "$sha_image" .
docker push "$sha_image"
if [ -n "$version" ]; then
    if [[ ! "$version" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        echo "Chyba: verze musí mít formát vX.Y.Z." >&2
        exit 2
    fi
    docker tag "$sha_image" "$repository:$version"
    docker push "$repository:$version"
fi

digest=$(docker inspect --format='{{index .RepoDigests 0}}' "$sha_image")
if [ -z "$digest" ]; then
    echo "Chyba: nepodařilo se zjistit publikovaný digest." >&2
    exit 1
fi
echo "$digest"
