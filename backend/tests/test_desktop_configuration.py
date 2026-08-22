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

        self.assertIn('configure-secrets.sh', script)
        self.assertIn('instances reset', script)
        self.assertIn('deploy.sh', script)
        self.assertNotIn('echo "$admin_token"', script)
        self.assertNotIn('echo "$database_password"', script)
