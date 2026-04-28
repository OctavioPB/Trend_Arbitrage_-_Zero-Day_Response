"""Database connection pool for the FastAPI backend.

Uses a thread-safe psycopg2 pool so sync endpoint functions (run by FastAPI in a
thread pool) don't starve each other. Lazy-initialised on first request.
"""

import contextlib
import logging
import os
from collections.abc import Generator

import psycopg2
import psycopg2.extras
import psycopg2.pool

logger = logging.getLogger(__name__)

_pool: psycopg2.pool.ThreadedConnectionPool | None = None


def _get_pool() -> psycopg2.pool.ThreadedConnectionPool:
    global _pool
    if _pool is None:
        dsn = os.environ.get(
            "POSTGRES_DSN",
            "postgresql://trend:trend@localhost:5432/trend_arbitrage",
        )
        _pool = psycopg2.pool.ThreadedConnectionPool(minconn=1, maxconn=10, dsn=dsn)
        logger.info("DB connection pool initialised (maxconn=10)")
    return _pool


def close_pool() -> None:
    """Close all connections. Call on application shutdown."""
    global _pool
    if _pool:
        _pool.closeall()
        _pool = None
        logger.info("DB connection pool closed")


@contextlib.contextmanager
def get_conn() -> Generator[psycopg2.extensions.connection, None, None]:
    """Borrow a connection from the pool and return it on exit."""
    pool = _get_pool()
    conn = pool.getconn()
    try:
        yield conn
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)
