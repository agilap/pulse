"""Database migration runner for Pulse."""
import os
from pathlib import Path

import psycopg

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


def get_conn():
    url = os.environ.get("DATABASE_URL", "postgresql://pulse:changeme-not-a-real-secret@localhost:5432/pulse")
    return psycopg.connect(url)


def ensure_meta_table(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)


def applied_versions(cur):
    cur.execute("SELECT version FROM schema_migrations ORDER BY version")
    return {row[0] for row in cur.fetchall()}


def migration_files():
    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    return [(f.stem, f.read_text()) for f in files]


def migrate():
    conn = get_conn()
    cur = conn.cursor()
    ensure_meta_table(cur)
    applied = applied_versions(cur)
    conn.commit()

    for version, sql in migration_files():
        if version in applied:
            print(f"  {version}: already applied, skipping")
            continue
        conn.execute("BEGIN")
        cur.execute(sql)
        cur.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (version,))
        conn.commit()
        print(f"  {version}: applied")

    cur.close()
    conn.close()
    print("Migrations complete.")


if __name__ == "__main__":
    migrate()
