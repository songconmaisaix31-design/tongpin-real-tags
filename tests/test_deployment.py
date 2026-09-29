from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from flask import Flask

import app.db as database_module
from app import create_app
from app.config import Config
from app.db import close_db, init_app as init_database
from tools.prepare_vercel_public import prepare_public_assets


class DeploymentTests(unittest.TestCase):
    def test_vercel_config_selects_flask_framework(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        config = json.loads((repo_root / "vercel.json").read_text(encoding="utf-8"))

        self.assertEqual(config["framework"], "flask")
        self.assertEqual(config["buildCommand"], "python tools/prepare_vercel_public.py")
        self.assertEqual(config["functions"]["index.py"]["maxDuration"], 20)

    def test_requirements_pin_the_remote_database_driver(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        requirements = (repo_root / "requirements.txt").read_text(encoding="utf-8").splitlines()

        self.assertIn("turso-serverless==0.1.0", requirements)

    def test_turso_credentials_must_be_paired_and_use_a_tls_url(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(database_module._turso_settings())

        with patch.dict(
            os.environ,
            {"TURSO_DATABASE_URL": "libsql://database.example.test"},
            clear=True,
        ):
            with self.assertRaisesRegex(RuntimeError, "configured together"):
                database_module._turso_settings()

        with patch.dict(
            os.environ,
            {
                "TURSO_DATABASE_URL": "http://database.example.test",
                "TURSO_AUTH_TOKEN": "test-token",
            },
            clear=True,
        ):
            with self.assertRaisesRegex(RuntimeError, "TLS Turso URL"):
                database_module._turso_settings()

    def test_turso_connection_uses_the_sqlite_compatible_row_factory(self) -> None:
        app = Flask("turso-connection-test")
        app.config.update(
            DATABASE="ignored.sqlite3",
            DEMO_MODE=False,
            REAL_USER_ONLY=True,
            SECRET_KEY="deployment-test-secret",
            SESSION_COOKIE_SECURE=True,
        )
        app.teardown_appcontext(close_db)
        connection = Mock()

        with (
            patch.dict(
                os.environ,
                {
                    "TURSO_DATABASE_URL": "libsql://database.example.test",
                    "TURSO_AUTH_TOKEN": "test-token",
                },
                clear=True,
            ),
            patch.object(
                database_module.turso_serverless,
                "connect",
                return_value=connection,
            ) as connect,
            app.app_context(),
        ):
            self.assertIs(database_module.get_db(), connection)
            self.assertIs(connection.row_factory, database_module.turso_serverless.Row)
            connection.execute.assert_called_once_with("PRAGMA foreign_keys = ON")
            connect.assert_called_once_with(
                "libsql://database.example.test",
                auth_token="test-token",
            )

    def test_turso_runtime_rejects_unsafe_real_user_settings(self) -> None:
        app = Flask("turso-runtime-test")
        app.config.update(
            DEMO_MODE=False,
            REAL_USER_ONLY=True,
            SECRET_KEY="deployment-test-secret",
            SESSION_COOKIE_SECURE=True,
        )
        with app.app_context():
            database_module._validate_turso_runtime()

        unsafe = (
            ("DEMO_MODE", True, "DEMO_MODE"),
            ("REAL_USER_ONLY", False, "REAL_USER_ONLY"),
            ("SECRET_KEY", "dev-only-change-me", "session secret"),
            ("SESSION_COOKIE_SECURE", False, "HTTPS-only"),
        )
        for key, value, message in unsafe:
            with self.subTest(key=key):
                original = app.config[key]
                app.config[key] = value
                try:
                    with app.app_context(), self.assertRaisesRegex(RuntimeError, message):
                        database_module._validate_turso_runtime()
                finally:
                    app.config[key] = original

    def test_database_path_environment_variable_is_used_at_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database = Path(temp_dir) / "runtime" / "realtags.sqlite3"
            config = type(
                "DeploymentConfig",
                (Config,),
                {"TESTING": True, "SECRET_KEY": "test", "DEMO_MODE": True},
            )

            with patch.dict(os.environ, {"DATABASE_PATH": str(database)}):
                app = create_app(config)

            self.assertEqual(app.config["DATABASE"], str(database))
            self.assertTrue(database.is_file())

    def test_explicit_database_config_takes_precedence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database = Path(temp_dir) / "explicit.sqlite3"
            config = type(
                "ExplicitDatabaseConfig",
                (Config,),
                {
                    "TESTING": True,
                    "DATABASE": str(database),
                    "SECRET_KEY": "test",
                    "DEMO_MODE": True,
                },
            )

            with patch.dict(os.environ, {"DATABASE_PATH": str(Path(temp_dir) / "ignored.sqlite3")}):
                app = create_app(config)

            self.assertEqual(app.config["DATABASE"], str(database))

    def test_database_init_does_not_write_to_the_flask_instance_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            blocked_parent = Path(temp_dir) / "not-a-directory"
            blocked_parent.write_text("block instance directory creation", encoding="utf-8")
            database = Path(temp_dir) / "runtime" / "realtags.sqlite3"
            app = Flask(
                "deployment-test",
                instance_path=str(blocked_parent / "instance"),
            )
            app.config.update(DATABASE=str(database), DEMO_MODE=True)
            app.teardown_appcontext(close_db)

            init_database(app)

            self.assertTrue(database.is_file())

    def test_public_asset_build_excludes_qa_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            for directory_name in ("css", "img", "js", "qa"):
                directory = repo_root / "app" / "static" / directory_name
                directory.mkdir(parents=True)
                (directory / "asset.txt").write_text(directory_name, encoding="utf-8")

            target = prepare_public_assets(repo_root)

            self.assertEqual(
                sorted(path.name for path in target.iterdir()),
                ["css", "img", "js"],
            )
            self.assertFalse((target / "qa").exists())


if __name__ == "__main__":
    unittest.main()
