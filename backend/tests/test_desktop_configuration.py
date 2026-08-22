import unittest
from pathlib import Path


class DesktopConfigurationTests(unittest.TestCase):
    def test_desktop_backend_is_pinned_to_file_storage(self) -> None:
        controller = (
            Path(__file__).resolve().parents[2] / "desktop" / "src" / "BackendController.cpp"
        ).read_text(encoding="utf-8")

        self.assertIn('"ESCAPEBOT_STORAGE_BACKEND"), QStringLiteral("json")', controller)
        self.assertIn('"ESCAPEBOT_DATA_DIR"', controller)
        self.assertIn('environment.remove(QStringLiteral("ESCAPEBOT_DATABASE_URL"))', controller)
        self.assertIn('QStringLiteral("--storage=json")', controller)

    def test_cloud_operator_keeps_admin_token_ephemeral(self) -> None:
        source = (
            Path(__file__).resolve().parents[2]
            / "desktop"
            / "src"
            / "CloudOperatorWindow.cpp"
        ).read_text(encoding="utf-8")

        self.assertIn('"secrets", "versions", "access", "latest"', source)
        self.assertIn("sessionStorage.setItem('escapeBotAdminToken'", source)
        self.assertNotIn('setValue("cloud/admin', source)
        self.assertNotIn("?admin_token=", source)

    def test_short_run_prepare_automates_secrets_without_printing_values(self) -> None:
        script = (
            Path(__file__).resolve().parents[2]
            / "deploy"
            / "gcp"
            / "prepare-short-run.sh"
        ).read_text(encoding="utf-8")

        self.assertIn('configure-admin-secret.sh', script)
        self.assertIn('instances reset', script)
        self.assertIn('deploy.sh', script)
        self.assertNotIn('echo "$admin_token"', script)
        self.assertNotIn('echo "$database_password"', script)

    def test_short_run_uses_json_without_cloud_sql(self) -> None:
        root = Path(__file__).resolve().parents[2]
        profile = (root / "infra" / "terraform" / "short-run.tfvars.example").read_text(encoding="utf-8")
        provision = (root / "deploy" / "gcp" / "provision-short-run.sh").read_text(encoding="utf-8")
        lifecycle = (root / "deploy" / "gcp" / "remote-event-lifecycle.sh").read_text(encoding="utf-8")
        deploy = (root / "deploy" / "gcp" / "remote-deploy.sh").read_text(encoding="utf-8")

        self.assertIn("enable_cloud_sql = false", profile)
        self.assertIn("-var=enable_cloud_sql=false", provision)
        self.assertIn("-v /srv/escape-bot/data:/data", lifecycle)
        self.assertNotIn("--backend postgres", lifecycle)
        self.assertIn('if [ "$storage_backend" = "postgres" ]', deploy)

    def test_short_run_state_and_configuration_are_portable(self) -> None:
        root = Path(__file__).resolve().parents[2]
        versions = (root / "infra" / "terraform" / "versions.tf").read_text(encoding="utf-8")
        provision = (root / "deploy" / "gcp" / "provision-short-run.sh").read_text(encoding="utf-8")
        loader = (root / "deploy" / "gcp" / "load-short-run-config.sh").read_text(encoding="utf-8")
        operator = (root / "desktop" / "src" / "CloudOperatorWindow.cpp").read_text(encoding="utf-8")

        self.assertIn('backend "gcs" {}', versions)
        self.assertIn('-backend-config="bucket=$state_bucket"', provision)
        self.assertIn("operator-config/$workspace.tfvars", provision)
        self.assertIn("terraform.tfstate.d", provision)
        self.assertIn("output -json", loader)
        self.assertIn("Navrhnout povinné hodnoty", operator)
        self.assertIn("Načíst existující prostředí", operator)
        self.assertIn("Vyhledat a převzít projekt", operator)
        self.assertIn('"projects", "list"', operator)
        self.assertIn('"storage", "buckets", "list"', operator)
        self.assertNotIn("ESCAPEBOT_ADMIN_TOKEN", loader)

        lifecycle = (root / "deploy" / "gcp" / "lifecycle-state.sh").read_text(encoding="utf-8")
        self.assertIn('state["deploy_count"] += 1', lifecycle)
        self.assertIn('state["live_run_count"] += 1', lifecycle)
        self.assertIn('state["history"]', lifecycle)
        self.assertIn("updateActionAvailability", operator)
        self.assertIn("m_resumeButton->setEnabled(!m_operationBusy && paused)", operator)
        self.assertIn("m_prepareLiveButton->setEnabled(!m_operationBusy && runningEnvironment)", operator)
        self.assertIn('tabs->addTab(controlPage, tr("Ovládání životního cyklu"))', operator)
        self.assertIn('tabs->addTab(dashboardPage, tr("Admin dashboard"))', operator)
        self.assertIn("controlPage->addWidget(operationsPanel)", operator)
