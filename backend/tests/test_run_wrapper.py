from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / "run.sh"


def invoke(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(RUN), *arguments],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def test_run_wrapper_has_valid_bash_syntax_and_documents_main_workflows() -> None:
    syntax = subprocess.run(["bash", "-n", str(RUN)], cwd=ROOT, check=False)
    assert syntax.returncode == 0

    result = invoke("help")
    assert result.returncode == 0
    assert "dev backend" in result.stdout
    assert "debug cloudflare" in result.stdout
    assert "deploy cloudflare staging|production" in result.stdout
    assert "deploy gcp" in result.stdout
    assert "sessions.json a lobbies.json" in result.stdout


def test_run_wrapper_rejects_unknown_or_incomplete_actions() -> None:
    unknown = invoke("unknown")
    assert unknown.returncode == 2
    assert "neznámý příkaz" in unknown.stderr

    incomplete = invoke("deploy", "gcp", "--project=test")
    assert incomplete.returncode == 2
    assert "--project, --zone, --vm a --image" in incomplete.stderr


def test_gcp_dry_run_requires_digest_and_never_contacts_server() -> None:
    tag_only = invoke(
        "deploy",
        "gcp",
        "--project=test-project",
        "--zone=europe-west3-a",
        "--vm=test-vm",
        "--image=europe-west3-docker.pkg.dev/test-project/escape-bot/app:latest",
        "--dry-run",
    )
    assert tag_only.returncode == 2
    assert "sha256 digestem" in tag_only.stderr

    digest = "a" * 64
    dry_run = invoke(
        "deploy",
        "gcp",
        "--project=test-project",
        "--zone=europe-west3-a",
        "--vm=test-vm",
        f"--image=europe-west3-docker.pkg.dev/test-project/escape-bot/app@sha256:{digest}",
        "--dry-run",
    )
    assert dry_run.returncode == 0
    assert dry_run.stdout.startswith("DRY-RUN:")
    assert "deploy/gcp/deploy.sh" in dry_run.stdout
    assert "test-vm" in dry_run.stdout


def test_remote_actions_require_confirmation_without_yes() -> None:
    digest = "b" * 64
    result = invoke(
        "deploy",
        "gcp",
        "--project=test-project",
        "--zone=europe-west3-a",
        "--vm=test-vm",
        f"--image=europe-west3-docker.pkg.dev/test-project/escape-bot/app@sha256:{digest}",
    )
    assert result.returncode == 2
    assert "interaktivní potvrzení nebo --yes" in result.stderr
