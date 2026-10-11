import os
from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
from psycopg_pool import ConnectionPool

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://pulse:changeme-not-a-real-secret@localhost:5432/pulse",
)

_pool: ConnectionPool | None = None


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(DATABASE_URL, min_size=1, max_size=20)
    return _pool


@contextmanager
def get_conn() -> Iterator[psycopg.Connection]:
    pool = get_pool()
    with pool.connection() as conn:
        yield conn


def close_pool():
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None
