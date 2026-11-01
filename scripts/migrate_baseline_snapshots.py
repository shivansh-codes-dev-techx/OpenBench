"""Apply or roll back the Phase 3B baseline tables in an existing SQLite DB.

Usage:
  python scripts/migrate_baseline_snapshots.py upgrade --db openbench.db
  python scripts/migrate_baseline_snapshots.py downgrade --db openbench.db

The migration takes an SQLite-consistent backup before either operation.
"""

from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


MIGRATION_ID = "20261031_resource_baseline_booking_snapshots"
LEDGER = "schema_migrations"
OWNED_TABLES = (
    "booking_baseline_snapshot_images",
    "booking_baseline_snapshots",
    "resource_baseline_images",
)

UP_SQL = (
    """CREATE TABLE resource_baseline_images (
        id INTEGER NOT NULL PRIMARY KEY,
        resource_id INTEGER NOT NULL,
        angle VARCHAR(10) NOT NULL,
        original_filename VARCHAR(255) NOT NULL,
        mime_type VARCHAR(50) NOT NULL,
        byte_size INTEGER NOT NULL,
        sha256 VARCHAR(64) NOT NULL,
        image_data BLOB NOT NULL,
        uploaded_by_id INTEGER NOT NULL,
        uploaded_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        quality_metadata JSON NOT NULL DEFAULT '{}',
        CONSTRAINT ck_resource_baseline_images_angle
            CHECK (angle IN ('FRONT','BACK','LEFT','RIGHT','TOP','BOTTOM')),
        CONSTRAINT uq_resource_baseline_images_resource_angle
            UNIQUE (resource_id, angle),
        FOREIGN KEY(resource_id) REFERENCES resources(id) ON DELETE CASCADE,
        FOREIGN KEY(uploaded_by_id) REFERENCES users(id)
    )""",
    """CREATE TABLE booking_baseline_snapshots (
        id INTEGER NOT NULL PRIMARY KEY,
        booking_id INTEGER NOT NULL,
        resource_id INTEGER NOT NULL,
        created_by_id INTEGER NOT NULL,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT uq_booking_baseline_snapshot_booking_resource
            UNIQUE (booking_id, resource_id),
        CONSTRAINT uq_booking_baseline_snapshot_id_booking
            UNIQUE (id, booking_id),
        FOREIGN KEY(booking_id) REFERENCES bookings(id) ON DELETE RESTRICT,
        FOREIGN KEY(resource_id) REFERENCES resources(id),
        FOREIGN KEY(created_by_id) REFERENCES users(id)
    )""",
    """CREATE TABLE booking_baseline_snapshot_images (
        id INTEGER NOT NULL PRIMARY KEY,
        snapshot_id INTEGER NOT NULL,
        booking_id INTEGER NOT NULL,
        angle VARCHAR(10) NOT NULL,
        source_baseline_image_id INTEGER,
        original_filename VARCHAR(255) NOT NULL,
        mime_type VARCHAR(50) NOT NULL,
        byte_size INTEGER NOT NULL,
        sha256 VARCHAR(64) NOT NULL,
        quality_metadata JSON NOT NULL DEFAULT '{}',
        image_data BLOB NOT NULL,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT ck_booking_baseline_snapshot_images_angle
            CHECK (angle IN ('FRONT','BACK','LEFT','RIGHT','TOP','BOTTOM')),
        CONSTRAINT uq_booking_baseline_snapshot_images_snapshot_angle
            UNIQUE (snapshot_id, angle),
        CONSTRAINT uq_booking_baseline_snapshot_images_booking_angle
            UNIQUE (booking_id, angle),
        CONSTRAINT fk_booking_baseline_snapshot_image_snapshot_booking
            FOREIGN KEY(snapshot_id, booking_id)
            REFERENCES booking_baseline_snapshots(id, booking_id) ON DELETE CASCADE,
        FOREIGN KEY(booking_id) REFERENCES bookings(id) ON DELETE RESTRICT,
        FOREIGN KEY(source_baseline_image_id)
            REFERENCES resource_baseline_images(id) ON DELETE SET NULL
    )""",
)

INDEX_SQL = (
    "CREATE INDEX ix_resource_baseline_images_id ON resource_baseline_images(id)",
    "CREATE INDEX ix_resource_baseline_images_resource_id ON resource_baseline_images(resource_id)",
    "CREATE INDEX ix_resource_baseline_images_uploaded_by_id ON resource_baseline_images(uploaded_by_id)",
    "CREATE INDEX ix_booking_baseline_snapshots_id ON booking_baseline_snapshots(id)",
    "CREATE UNIQUE INDEX ix_booking_baseline_snapshots_booking_id ON booking_baseline_snapshots(booking_id)",
    "CREATE INDEX ix_booking_baseline_snapshots_resource_id ON booking_baseline_snapshots(resource_id)",
    "CREATE INDEX ix_booking_baseline_snapshots_created_by_id ON booking_baseline_snapshots(created_by_id)",
    "CREATE INDEX ix_booking_baseline_snapshot_images_id ON booking_baseline_snapshot_images(id)",
    "CREATE INDEX ix_booking_baseline_snapshot_images_snapshot_id ON booking_baseline_snapshot_images(snapshot_id)",
    "CREATE INDEX ix_booking_baseline_snapshot_images_booking_id ON booking_baseline_snapshot_images(booking_id)",
)


def make_backup(db_path: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup_path = db_path.with_name(f"{db_path.name}.{stamp}.bak")
    if backup_path.exists():
        raise FileExistsError(f"Refusing to overwrite backup: {backup_path}")
    source = sqlite3.connect(str(db_path))
    destination = sqlite3.connect(str(backup_path))
    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()
    return backup_path


def _open(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), isolation_level=None)
    conn.execute("PRAGMA foreign_keys = ON")
    if conn.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
        conn.close()
        raise RuntimeError("SQLite foreign-key enforcement could not be enabled")
    return conn


def _tables(conn: sqlite3.Connection) -> set[str]:
    return {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }


def _ensure_parent_schema(conn: sqlite3.Connection) -> None:
    tables = _tables(conn)
    missing = {"resources", "bookings", "users"} - tables
    if missing:
        raise RuntimeError(
            "Database is missing required existing tables: " + ", ".join(sorted(missing))
        )


def _normalize_sql(sql: str) -> str:
    return " ".join(sql.replace('"', "").replace("`", "").split()).upper()


def _verify_applied_schema(conn: sqlite3.Connection) -> None:
    """Fail closed if the ledger claims success but any owned schema drifted."""
    expected_tables = {
        statement.split("(", 1)[0].replace("CREATE TABLE", "").strip(): statement
        for statement in UP_SQL
    }
    for table_name, expected_sql in expected_tables.items():
        row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        ).fetchone()
        if row is None or _normalize_sql(row[0]) != _normalize_sql(expected_sql):
            raise RuntimeError(
                f"Recorded baseline migration has missing or altered table: {table_name}"
            )

    for statement in INDEX_SQL:
        index_name = statement.split("INDEX", 1)[1].split(" ON ", 1)[0].strip()
        row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='index' AND name=?",
            (index_name,),
        ).fetchone()
        if row is None or _normalize_sql(row[0]) != _normalize_sql(statement):
            raise RuntimeError(
                f"Recorded baseline migration has missing or altered index: {index_name}"
            )

    violations = list(conn.execute("PRAGMA foreign_key_check"))
    if violations:
        raise RuntimeError(f"Recorded baseline migration has FK violations: {violations!r}")


def upgrade(db_path: Path) -> Path:
    if not db_path.is_file():
        raise FileNotFoundError(f"Database file does not exist: {db_path}")
    backup_path = make_backup(db_path)
    conn = _open(db_path)
    try:
        _ensure_parent_schema(conn)
        tables = _tables(conn)
        collision = set(OWNED_TABLES) & tables
        if LEDGER in tables:
            applied = conn.execute(
                f"SELECT 1 FROM {LEDGER} WHERE migration_id = ?", (MIGRATION_ID,)
            ).fetchone()
            if applied:
                _verify_applied_schema(conn)
                return backup_path
        if collision:
            raise RuntimeError(
                "Refusing to overwrite untracked baseline tables: "
                + ", ".join(sorted(collision))
            )

        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            f"""CREATE TABLE IF NOT EXISTS {LEDGER} (
                migration_id TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        for statement in UP_SQL:
            conn.execute(statement)
        for statement in INDEX_SQL:
            conn.execute(statement)
        conn.execute(
            f"INSERT INTO {LEDGER}(migration_id) VALUES (?)", (MIGRATION_ID,)
        )
        violations = list(conn.execute("PRAGMA foreign_key_check"))
        if violations:
            raise RuntimeError(f"Foreign-key check failed: {violations!r}")
        conn.execute("COMMIT")
        return backup_path
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()


def downgrade(db_path: Path) -> Path:
    if not db_path.is_file():
        raise FileNotFoundError(f"Database file does not exist: {db_path}")
    backup_path = make_backup(db_path)
    conn = _open(db_path)
    try:
        tables = _tables(conn)
        if LEDGER not in tables or conn.execute(
            f"SELECT 1 FROM {LEDGER} WHERE migration_id = ?", (MIGRATION_ID,)
        ).fetchone() is None:
            raise RuntimeError("Baseline migration is not recorded as applied")
        present = set(OWNED_TABLES) & tables
        if present != set(OWNED_TABLES):
            raise RuntimeError("Refusing rollback: expected baseline tables are incomplete")
        conn.execute("BEGIN IMMEDIATE")
        for table_name in OWNED_TABLES:
            conn.execute(f'DROP TABLE "{table_name}"')
        conn.execute(
            f"DELETE FROM {LEDGER} WHERE migration_id = ?", (MIGRATION_ID,)
        )
        violations = list(conn.execute("PRAGMA foreign_key_check"))
        if violations:
            raise RuntimeError(f"Foreign-key check failed after rollback: {violations!r}")
        conn.execute("COMMIT")
        return backup_path
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("upgrade", "downgrade"))
    parser.add_argument("--db", type=Path, required=True)
    args = parser.parse_args()
    db_path = args.db.resolve()
    backup = upgrade(db_path) if args.action == "upgrade" else downgrade(db_path)
    print(f"{args.action} complete; backup: {backup}")


if __name__ == "__main__":
    main()
