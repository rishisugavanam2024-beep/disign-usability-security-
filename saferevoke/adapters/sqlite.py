"""Explicitly scoped SQLite test snapshots; no production-database discovery."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import sqlite3
import time

from saferevoke.adapters.callback import StateHooks


@dataclass
class SQLiteSnapshot:
    _connection: sqlite3.Connection
    _owner: object
    digest: str
    closed: bool = False

    def close(self):
        if not self.closed:
            self._connection.close()
            self.closed = True


class SQLiteTestState:
    """Back up and restore one small, quiescent SQLite test database.

    Caller supplies a dedicated test root and permission mutation callback. This
    helper does not infer schemas, close application transactions, reset Python
    caches, or undo queues/network writes. Stop background writers before use.
    """

    def __init__(self, path, *, test_root, remove_grants, test_environment=False,
                 timeout=5.0, max_database_bytes=32_000_000):
        if test_environment is not True:
            raise ValueError("Enable snapshots only for an isolated test database")
        source, root = Path(path).absolute(), Path(test_root).resolve(strict=True)
        if not root.is_dir() or source.is_symlink():
            raise ValueError("Use a real test directory and a non-symlink database file")
        source = source.resolve(strict=True)
        if not source.is_relative_to(root) or not source.is_file():
            raise ValueError("The SQLite file must be inside the explicitly selected test root")
        if timeout <= 0 or max_database_bytes <= 0 or not callable(remove_grants):
            raise ValueError("Provide a mutation callback and positive backup limits")
        self.path, self.timeout = source, timeout
        self.remove_grants, self.max_database_bytes = remove_grants, max_database_bytes
        self._owner = object()

    def _open(self, *, write=False):
        # mode=rw/ro never creates a new database if the selected file disappears.
        return sqlite3.connect(self.path.as_uri() + ("?mode=rw" if write else "?mode=ro"),
                               uri=True, timeout=self.timeout)

    @staticmethod
    def _digest(connection):
        digest = hashlib.sha256()
        for line in connection.iterdump():
            digest.update(line.encode("utf-8"))
            digest.update(b"\n")
        return digest.hexdigest()

    def _backup(self, source, destination):
        deadline = time.monotonic() + self.timeout

        def progress(status, remaining, total):
            if time.monotonic() > deadline:
                raise TimeoutError("SQLite backup/restore deadline exceeded; stop testing")

        source.backup(destination, pages=128, progress=progress, sleep=0.01)

    def snapshot(self):
        memory = sqlite3.connect(":memory:")
        try:
            source = self._open()
            try:
                size = source.execute("PRAGMA page_count").fetchone()[0] * source.execute("PRAGMA page_size").fetchone()[0]
                if size > self.max_database_bytes:
                    raise ValueError("Database exceeds the configured test snapshot size limit")
                self._backup(source, memory)
            finally:
                source.close()
            return SQLiteSnapshot(memory, self._owner, self._digest(memory))
        except BaseException:
            memory.close()
            raise

    def restore(self, snapshot):
        if not isinstance(snapshot, SQLiteSnapshot) or snapshot._owner is not self._owner or snapshot.closed:
            raise ValueError("Snapshot is closed or belongs to a different test database helper")
        try:
            destination = self._open(write=True)
            try:
                self._backup(snapshot._connection, destination)
                if self._digest(destination) != snapshot.digest:
                    raise RuntimeError("SQLite test database restoration could not be verified")
            finally:
                destination.close()
        finally:
            snapshot.close()

    def matches_snapshot(self, snapshot):
        if not isinstance(snapshot, SQLiteSnapshot) or snapshot._owner is not self._owner:
            return False
        connection = self._open()
        try:
            return self._digest(connection) == snapshot.digest
        finally:
            connection.close()

    @property
    def hooks(self):
        return StateHooks(self.snapshot, self.remove_grants, self.restore)
