import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.database import local_sqlite_configuration, prepare_private_sqlite_file


class DatabaseConfigurationTest(unittest.TestCase):
    def test_local_sqlite_urls_resolve_to_the_same_database_path(self):
        relative_path = Path("home_erp.db")
        absolute_path = relative_path.resolve()
        for value in (
            "sqlite:///./home_erp.db",
            "sqlite+pysqlite:///" + absolute_path.as_posix(),
        ):
            with self.subTest(value=value):
                url, path = local_sqlite_configuration(value)
                self.assertEqual(path, absolute_path)
                self.assertEqual(Path(url.database), absolute_path)

    def test_in_memory_sqlite_is_available_without_a_backup_path(self):
        for value in ("sqlite://", "sqlite:///:memory:"):
            with self.subTest(value=value):
                _, path = local_sqlite_configuration(value)
                self.assertIsNone(path)

    def test_remote_and_sqlite_uri_configurations_are_rejected(self):
        for value in (
            "postgresql://database.example/tracker",
            "sqlite://database.example/tracker.db",
            r"sqlite:///\\database.example\share\tracker.db",
            "sqlite://///database.example/share/tracker.db",
            "sqlite:///file:tracker.db?uri=true",
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                local_sqlite_configuration(value)

    @unittest.skipUnless(os.name == "nt", "uses Windows drive types")
    def test_mapped_windows_drive_is_rejected_before_resolving_the_path(self):
        with patch("ctypes.windll.kernel32.GetDriveTypeW", return_value=4) as drive_type:
            with patch("app.local_paths.Path.resolve") as resolve, self.assertRaises(ValueError):
                local_sqlite_configuration("sqlite:///Z:/tracker.db")
        drive_type.assert_called_once_with("Z:\\")
        resolve.assert_not_called()

    @unittest.skipUnless(os.name == "posix", "uses POSIX file permissions")
    def test_live_and_backup_files_use_owner_only_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            existing_file = folder / "current.db"
            existing_file.write_bytes(b"existing database")
            existing_file.chmod(0o644)
            prepare_private_sqlite_file(existing_file)
            self.assertEqual(existing_file.stat().st_mode & 0o777, 0o600)
            self.assertEqual(existing_file.read_bytes(), b"existing database")

            backup_file = folder / "current.db.backup"
            prepare_private_sqlite_file(backup_file)
            self.assertEqual(backup_file.stat().st_mode & 0o777, 0o600)
