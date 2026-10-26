import asyncio
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from replay import initialize, reserve


class Sql:
    def __init__(self, connection):
        self.connection = connection

    def exec(self, statement, *params):
        cursor = self.connection.execute(statement, params)
        rows = cursor.fetchall()
        self.connection.commit()
        return type("Cursor", (), {"toArray": lambda self: rows})()


class ReplayTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        self.addCleanup(self.connection.close)
        self.sql = Sql(self.connection)
        initialize(self.sql)

    async def test_concurrent_duplicate_claims_have_one_winner(self):
        async def claim():
            return reserve(self.sql, "same-hash", 2000, 1000)
        results = await asyncio.gather(*(claim() for _ in range(20)))
        self.assertEqual(results.count(True), 1)

    async def test_expiry_and_independent_nonces(self):
        self.assertTrue(reserve(self.sql, "first", 2000, 1000))
        self.assertTrue(reserve(self.sql, "second", 3000, 1500))
        self.assertFalse(reserve(self.sql, "first", 3000, 1999))
        self.assertTrue(reserve(self.sql, "first", 4000, 2000))
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM nonces").fetchone()[0], 2)

    async def test_records_survive_reopening_storage(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "nonces.sqlite"
            connection = sqlite3.connect(database)
            sql = Sql(connection)
            initialize(sql)
            self.assertTrue(reserve(sql, "persistent", 2000, 1000))
            connection.close()
            connection = sqlite3.connect(database)
            try:
                sql = Sql(connection)
                initialize(sql)
                self.assertFalse(reserve(sql, "persistent", 3000, 1500))
            finally:
                connection.close()
