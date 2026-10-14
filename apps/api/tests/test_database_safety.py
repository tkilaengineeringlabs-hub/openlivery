"""Run without the destructive pytest fixture using unittest discovery."""

import os
from pathlib import Path
import subprocess
import sys
import unittest

from database_safety import is_disposable_test_target


class DatabaseSafetyTests(unittest.TestCase):
    def test_rejects_unsafe_or_ambiguous_targets(self):
        for url in (
            "", "not a URL", "sqlite:///local_test",
            "postgresql+psycopg://user@db/live_test",
            "postgresql+psycopg://user@remote.example/app_test",
            "postgresql+psycopg://user@localhost/app",
            "postgresql+psycopg://user@localhost/app_test?host=remote.example",
            "postgresql+psycopg://user@localhost/app_test?service=production",
        ):
            with self.subTest(url=url):
                self.assertFalse(is_disposable_test_target(url, "1"))

    def test_requires_explicit_reset_consent_even_for_local_test_database(self):
        for host in ("localhost", "127.0.0.1", "[::1]", "db-test"):
            url = f"postgresql+psycopg://user@{host}/app_test"
            with self.subTest(host=host):
                self.assertTrue(is_disposable_test_target(url, "1"))
                self.assertFalse(is_disposable_test_target(url, None))
                self.assertFalse(is_disposable_test_target(url, "0"))

    def test_application_settings_are_isolated_before_import(self):
        result = subprocess.run(
            [sys.executable, "-c", """
import sys
sys.path.insert(0, 'tests')
import conftest
from app.config import Settings, get_settings
settings = get_settings()
assert Settings.model_config['env_file'] is None
assert settings.database_url.endswith('/isolated_test')
assert str(settings.storage_dir) != '/must-not-touch'
assert settings.storage_dir.is_dir()
assert settings.secret_key != 'inherited-fixture-secret'
assert not settings.social_worker_enabled
assert settings.push_provider == 'none'
print('Application settings isolation passed')
"""],
            cwd=Path(__file__).resolve().parents[1],
            env={
                **os.environ,
                "TEST_DATABASE_URL": "postgresql+psycopg://test@localhost/isolated_test",
                "TKILA_TEST_ALLOW_RESET": "1",
                "DATABASE_URL": "postgresql+psycopg://test@remote.example/do_not_touch",
                "STORAGE_DIR": "/must-not-touch",
                "SECRET_KEY": "inherited-fixture-secret",
                "SOCIAL_WORKER_ENABLED": "true",
                "PUSH_PROVIDER": "webhook",
            },
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Application settings isolation passed", result.stdout)
