#!/bin/bash
set -euo pipefail

if [ "$#" -lt 4 ] || [ "$#" -gt 5 ]; then
    echo "Použití: $0 get|update PROJECT BUCKET ENVIRONMENT [EVENT]" >&2
    exit 2
fi
action="$1"; project="$2"; bucket="$3"; environment="$4"; event="${5:-}"
object="gs://$bucket/escape-bot/operator-state/$environment.json"
temporary=$(mktemp)
trap 'rm -f "$temporary"' EXIT

if ! gcloud storage cat "$object" --project="$project" >"$temporary" 2>/dev/null; then
    printf '{"phase":"unknown","deploy_count":0,"live_run_count":0,"archive_count":0,"history":[]}' >"$temporary"
fi
if [ "$action" = "get" ]; then
    cat "$temporary"
    exit 0
fi
if [ "$action" != "update" ] || [ -z "$event" ]; then
    echo "Chyba: update vyžaduje událost." >&2
    exit 2
fi

python3 - "$temporary" "$event" <<'PY'
import json
import sys
from datetime import UTC, datetime

path, event = sys.argv[1:]
with open(path, encoding="utf-8") as source:
    state = json.load(source)
state.setdefault("deploy_count", 0)
state.setdefault("live_run_count", 0)
state.setdefault("archive_count", 0)
state.setdefault("history", [])
phase = state.get("phase", "unknown")
if event == "infrastructure_ready":
    phase = "infrastructure_ready"
elif event == "prepared_test":
    phase = "testing"
    state["deploy_count"] += 1
elif event == "deployed_fix":
    state["deploy_count"] += 1
elif event == "live_prepared":
    phase = "ready_for_live"
    state["live_run_count"] += 1
elif event == "paused":
    if phase != "paused":
        state["phase_before_pause"] = phase
    phase = "paused"
elif event == "resumed":
    phase = state.pop("phase_before_pause", "testing")
elif event == "archived":
    state["archive_count"] += 1
elif event == "destroyed":
    phase = "destroyed"
    state["archive_count"] += 1
else:
    raise SystemExit(f"Neznámá lifecycle událost: {event}")
state["phase"] = phase
state["updated_at"] = datetime.now(UTC).isoformat()
state["history"] = (state["history"] + [{"event": event, "at": state["updated_at"]}])[-50:]
with open(path, "w", encoding="utf-8") as destination:
    json.dump(state, destination, ensure_ascii=False, indent=2)
    destination.write("\n")
PY
gcloud storage cp "$temporary" "$object" --project="$project" >/dev/null
cat "$temporary"
