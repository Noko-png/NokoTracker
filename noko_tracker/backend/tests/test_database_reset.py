import unittest
from unittest.mock import patch

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine, event, select, func

from app import models
from app.routers import database_reset
from app.security import Principal, current_principal


class DatabaseResetTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        self.addCleanup(self.engine.dispose)
        event.listen(self.engine, "connect", lambda connection, _: connection.execute("PRAGMA foreign_keys=ON"))
        models.Base.metadata.create_all(self.engine)
        with self.engine.begin() as connection:
            connection.execute(models.User.__table__.insert().values(id=1, username="Test", password="!"))
            connection.execute(models.WeightEntry.__table__.insert().values(user_id=1, weight_kg=80))
        mock = patch.object(database_reset, "engine", self.engine)
        mock.start()
        self.addCleanup(mock.stop)
        token = current_principal.set(Principal(None, True))
        self.addCleanup(current_principal.reset, token)
        self.confirmation = database_reset.ResetConfirmation(confirmation="ALLE DATEN LOESCHEN")

    def count(self, table):
        with self.engine.connect() as connection:
            return connection.scalar(select(func.count()).select_from(table))

    def test_reset_clears_all_tables_and_preserves_usable_schema(self):
        database_reset.reset_database(self.confirmation)
        for table in models.Base.metadata.sorted_tables:
            self.assertEqual(self.count(table), 0)
        with self.engine.begin() as connection:
            connection.execute(models.User.__table__.insert().values(username="New", password="!"))
        self.assertEqual(self.count(models.User.__table__), 1)

    def test_non_admin_cannot_reset(self):
        current_principal.set(Principal(1, False))
        with self.assertRaises(HTTPException) as error:
            database_reset.reset_database(self.confirmation)
        self.assertEqual(error.exception.status_code, 403)
        self.assertEqual(self.count(models.User.__table__), 1)

    def test_confirmation_is_required(self):
        for payload in ({}, {"confirmation": "yes"}):
            with self.assertRaises(ValidationError):
                database_reset.ResetConfirmation(**payload)

    def test_failure_rolls_back_prior_deletions(self):
        def fail_on_users(connection, cursor, statement, parameters, context, executemany):
            if statement.startswith("DELETE FROM users"):
                raise RuntimeError("simulated failure")
        event.listen(self.engine, "before_cursor_execute", fail_on_users)
        with self.assertRaises(RuntimeError):
            database_reset.reset_database(self.confirmation)
        self.assertEqual(self.count(models.User.__table__), 1)
        self.assertEqual(self.count(models.WeightEntry.__table__), 1)
