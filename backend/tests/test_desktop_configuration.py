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
