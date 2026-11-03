"""Conexões SQLite com integridade referencial habilitada explicitamente."""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def connect_database(path: Path, *, read_only: bool = False) -> Iterator[sqlite3.Connection]:
    """O chamador controla a transação; a conexão sempre é encerrada."""
    location = path.resolve().as_uri() + "?mode=ro" if read_only else path
    connection = sqlite3.connect(location, uri=read_only, isolation_level=None, timeout=5)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        if read_only:
            connection.execute("PRAGMA query_only = ON")
        yield connection
    finally:
        connection.close()
