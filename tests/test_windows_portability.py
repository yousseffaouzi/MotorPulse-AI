"""Windows-specific unittest portability guards.

The production code uses explicit SQLiteHistory.close() semantics. A few migration
fixtures also use the stdlib sqlite3 connection context manager directly. That
context manager commits or rolls back but does not close the connection, which can
leave a Windows file handle alive long enough for TemporaryDirectory cleanup to
fail with WinError 32. The full-suite test harness makes those raw fixture
connections close on context-manager exit on Windows only.
"""

from __future__ import annotations

import os
import sqlite3
import unittest

from motorpulse.export import _canonical_source_bytes

_ORIGINAL_CONNECT = sqlite3.connect


class _ClosingConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


def _closing_connect(*args, **kwargs):
    kwargs.setdefault("factory", _ClosingConnection)
    return _ORIGINAL_CONNECT(*args, **kwargs)


if os.name == "nt":
    sqlite3.connect = _closing_connect


class CrossPlatformSourceHashTests(unittest.TestCase):
    def test_source_hash_bytes_normalize_crlf_and_cr_to_lf(self):
        self.assertEqual(_canonical_source_bytes(b"alpha\r\nbeta\r\n"), b"alpha\nbeta\n")
        self.assertEqual(_canonical_source_bytes(b"alpha\rbeta\r"), b"alpha\nbeta\n")
        self.assertEqual(_canonical_source_bytes(b"alpha\nbeta\n"), b"alpha\nbeta\n")


class WindowsSQLiteFixtureTests(unittest.TestCase):
    def test_raw_sqlite_context_closes_on_windows(self):
        if os.name != "nt":
            self.skipTest("Windows-only sqlite fixture behavior")
        with sqlite3.connect(":memory:") as connection:
            self.assertEqual(connection.execute("SELECT 1").fetchone()[0], 1)
        with self.assertRaises(sqlite3.ProgrammingError):
            connection.execute("SELECT 1")


if __name__ == "__main__":
    unittest.main()
