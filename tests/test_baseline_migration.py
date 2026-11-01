import sqlite3

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.schema import UniqueConstraint

from app.database import Base
from app.models.booking_baseline_snapshot import (
    BookingBaselineSnapshot,
    BookingBaselineSnapshotImage,
)
from app.models.resource_baseline_image import ResourceBaselineImage

from scripts.migrate_baseline_snapshots import (
    LEDGER,
    MIGRATION_ID,
    OWNED_TABLES,
    downgrade,
    upgrade,
)


def make_existing_database(path):
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            PRAGMA foreign_keys=ON;
            CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT NOT NULL);
            CREATE TABLE resources (
                id INTEGER PRIMARY KEY,
                owner_id INTEGER NOT NULL REFERENCES users(id)
            );
            CREATE TABLE bookings (
                id INTEGER PRIMARY KEY,
                resource_id INTEGER NOT NULL REFERENCES resources(id)
            );
            CREATE TABLE existing_records (id INTEGER PRIMARY KEY, value TEXT NOT NULL);
            INSERT INTO users VALUES (7, 'keep@example.test');
            INSERT INTO resources VALUES (8, 7);
            INSERT INTO bookings VALUES (9, 8);
            INSERT INTO existing_records VALUES (1, 'preserve me');
            """
        )


def read_tables(path):
    with sqlite3.connect(path) as conn:
        return {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }


def test_upgrade_makes_backup_preserves_existing_data_and_enables_integrity(tmp_path):
    db_path = tmp_path / "openbench.db"
    make_existing_database(db_path)

    backup = upgrade(db_path)

    assert backup.is_file()
    assert read_tables(backup) == {
        "users", "resources", "bookings", "existing_records"
    }
    assert set(OWNED_TABLES).issubset(read_tables(db_path))
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT value FROM existing_records WHERE id=1").fetchone() == (
            "preserve me",
        )
        assert conn.execute("SELECT email FROM users WHERE id=7").fetchone() == (
            "keep@example.test",
        )
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 0
        conn.execute("PRAGMA foreign_keys=ON")
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert conn.execute(
            f"SELECT migration_id FROM {LEDGER}"
        ).fetchone() == (MIGRATION_ID,)
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_upgrade_retry_does_not_duplicate_schema_or_ledger_row(tmp_path):
    db_path = tmp_path / "openbench.db"
    make_existing_database(db_path)
    upgrade(db_path)

    second_backup = upgrade(db_path)

    assert second_backup.is_file()
    with sqlite3.connect(db_path) as conn:
        assert conn.execute(
            f"SELECT COUNT(*) FROM {LEDGER} WHERE migration_id=?", (MIGRATION_ID,)
        ).fetchone()[0] == 1
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


@pytest.mark.parametrize(
    ("corruption", "expected_message"),
    [
        ("drop_table", "missing or altered table"),
        ("drop_index", "missing or altered index"),
    ],
)
def test_upgrade_retry_rejects_recorded_but_incomplete_schema(
    tmp_path, corruption, expected_message
):
    db_path = tmp_path / "openbench.db"
    make_existing_database(db_path)
    upgrade(db_path)
    with sqlite3.connect(db_path) as conn:
        if corruption == "drop_table":
            conn.execute("DROP TABLE resource_baseline_images")
        else:
            conn.execute("DROP INDEX ix_booking_baseline_snapshots_resource_id")

    with pytest.raises(RuntimeError, match=expected_message):
        upgrade(db_path)


def _normalize_check(expression):
    return "".join(expression.upper().split()).replace('"', "")


def test_migrated_schema_matches_sqlalchemy_baseline_models(tmp_path):
    db_path = tmp_path / "openbench.db"
    make_existing_database(db_path)
    upgrade(db_path)
    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    inspector = inspect(engine)

    for model in (
        ResourceBaselineImage,
        BookingBaselineSnapshot,
        BookingBaselineSnapshotImage,
    ):
        table = model.__table__
        name = table.name
        actual_columns = {
            (column["name"], column["nullable"], bool(column["primary_key"]))
            for column in inspector.get_columns(name)
        }
        expected_columns = {
            (column.name, column.nullable, bool(column.primary_key))
            for column in table.columns
        }
        assert actual_columns == expected_columns, name

        actual_uniques = {
            frozenset(constraint["column_names"])
            for constraint in inspector.get_unique_constraints(name)
        }
        expected_uniques = {
            frozenset(constraint.columns.keys())
            for constraint in table.constraints
            if isinstance(constraint, UniqueConstraint)
        }
        assert actual_uniques == expected_uniques, name

        actual_checks = {
            _normalize_check(constraint["sqltext"])
            for constraint in inspector.get_check_constraints(name)
        }
        expected_checks = {
            _normalize_check(constraint.sqltext.text)
            for constraint in table.constraints
            if constraint.__class__.__name__ == "CheckConstraint"
        }
        assert actual_checks == expected_checks, name

        actual_fks = {
            (
                tuple(foreign_key["constrained_columns"]),
                foreign_key["referred_table"],
                tuple(foreign_key["referred_columns"]),
                (foreign_key.get("options") or {}).get("ondelete"),
            )
            for foreign_key in inspector.get_foreign_keys(name)
        }
        expected_fks = {
            (
                tuple(constraint.columns.keys()),
                next(iter(constraint.elements)).column.table.name,
                tuple(element.column.name for element in constraint.elements),
                next(iter(constraint.elements)).ondelete,
            )
            for constraint in table.constraints
            if constraint.__class__.__name__ == "ForeignKeyConstraint"
        }
        assert actual_fks == expected_fks, name

        actual_indexes = {
            (index["name"], tuple(index["column_names"]), bool(index["unique"]))
            for index in inspector.get_indexes(name)
        }
        expected_indexes = {
            (index.name, tuple(column.name for column in index.columns), bool(index.unique))
            for index in table.indexes
        }
        assert actual_indexes == expected_indexes, name

    engine.dispose()


def test_upgrade_failure_rolls_back_all_new_tables_and_keeps_backup(tmp_path):
    db_path = tmp_path / "openbench.db"
    make_existing_database(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE resource_baseline_images (id INTEGER PRIMARY KEY)")
    before = read_tables(db_path)

    with pytest.raises(RuntimeError, match="untracked baseline tables"):
        upgrade(db_path)

    assert read_tables(db_path) == before
    assert len(list(tmp_path.glob("openbench.db.*.bak"))) == 1


def test_rollback_removes_only_phase3b_tables_and_keeps_existing_data(tmp_path):
    db_path = tmp_path / "openbench.db"
    make_existing_database(db_path)
    upgrade(db_path)

    backup = downgrade(db_path)

    assert backup.is_file()
    assert not (set(OWNED_TABLES) & read_tables(db_path))
    assert LEDGER in read_tables(db_path)
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT value FROM existing_records").fetchone() == (
            "preserve me",
        )
        assert conn.execute(
            f"SELECT COUNT(*) FROM {LEDGER} WHERE migration_id=?", (MIGRATION_ID,)
        ).fetchone()[0] == 0


def test_rollback_requires_applied_migration_record(tmp_path):
    db_path = tmp_path / "openbench.db"
    make_existing_database(db_path)

    with pytest.raises(RuntimeError, match="not recorded as applied"):
        downgrade(db_path)


def test_snapshot_angle_and_source_foreign_key_constraints_are_present(tmp_path):
    db_path = tmp_path / "openbench.db"
    make_existing_database(db_path)
    upgrade(db_path)

    with sqlite3.connect(db_path) as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """INSERT INTO resource_baseline_images
                (resource_id, angle, original_filename, mime_type, byte_size,
                 sha256, image_data, uploaded_by_id)
                VALUES (8, 'DIAGONAL', 'bad.png', 'image/png', 1, 'x', X'00', 7)"""
            )
        conn.rollback()
        foreign_keys = conn.execute(
            "PRAGMA foreign_key_list(booking_baseline_snapshot_images)"
        ).fetchall()
        assert any(row[2] == "resource_baseline_images" for row in foreign_keys)
        booking_fk = next(row for row in foreign_keys if row[2] == "bookings")
        assert booking_fk[6] == "RESTRICT"
