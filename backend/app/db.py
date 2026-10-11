import os
from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
from psycopg_pool import ConnectionPool

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://pulse:pulse@localhost:5432/pulse",
)

_pool: ConnectionPool | None = None


def get_pool() -> ConnectionPool:
    """Lazily initialize and return the shared connection pool."""
    global _pool
    if _pool is None:
        _pool = ConnectionPool(DATABASE_URL, min_size=1, max_size=20)
    return _pool


@contextmanager
def get_conn() -> Iterator[psycopg.Connection]:
    """Context manager yielding a connection from the pool.

    Usage:
        with get_conn() as conn:
            cur = conn.execute("SELECT 1")
    """
    pool = get_pool()
    with pool.connection() as conn:
        yield conn


def close_pool():
    """Close the pool — call on app shutdown."""
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None
