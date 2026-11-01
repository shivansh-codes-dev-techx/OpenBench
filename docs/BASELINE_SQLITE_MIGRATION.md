# Phase 3B SQLite migration

The repository has no migration framework. This migration uses a small, explicit
SQLite script and does not recreate the database or alter existing tables.

## Scope

Upgrade creates the three Phase 3B domain tables
(`resource_baseline_images`, `booking_baseline_snapshots`, and
`booking_baseline_snapshot_images`), their indexes, constraints, and foreign
keys. It also creates `schema_migrations`, a small tracking ledger used to
prevent duplicate application. Existing tables and records are left intact.
SQLite foreign-key enforcement is enabled and checked on the migration
connection; `PRAGMA foreign_key_check` runs before commit.

Booking references from the snapshot tables are restrictive so an application
booking deletion cannot discard its frozen baseline. Snapshot ORM records also
reject normal SQLAlchemy updates and deletes. Resource baseline replacement
updates only the resource baseline row; snapshots contain copied image bytes and
remain unchanged. The ORM listeners are application-level safeguards: direct SQL
or bulk operations executed outside ordinary ORM persistence can bypass them.
Snapshot reads verify SHA256 and report altered bytes, but this is detection rather
than a database-level write lock. Access to the SQLite file must remain restricted
to trusted application and migration processes.

The booking snapshot API returns snapshot metadata and per-angle image URLs from
`GET /bookings/{booking_id}/baseline-snapshot`. Retrieve an individual image as
binary from `GET /bookings/{booking_id}/baseline-snapshot/{angle}` rather than
embedding all six images as Base64 in one JSON response. Both endpoints apply the
same booking student/resource owner/admin authorization and integrity checks.

## Backup and upgrade

Stop application processes that write to the database and verify the database
path before running the command. The script creates a consistent SQLite backup
beside the database before changing it. It refuses to overwrite a backup.

```powershell
.\.venv\Scripts\python.exe scripts\migrate_baseline_snapshots.py upgrade --db .\openbench.db
```

The command reports the backup path. Keep that backup until the upgraded
application has been reviewed. Upgrade work runs in one `BEGIN IMMEDIATE`
transaction; a failure rolls back the tables and tracking row together. A
repeat upgrade is a no-op when the migration ID is already recorded.

## Rollback

The rollback creates its own pre-rollback backup, then drops only the three
Phase 3B tables in child-to-parent order. It removes the migration ledger row
but retains `schema_migrations` and every unrelated table.

```powershell
.\.venv\Scripts\python.exe scripts\rollback_baseline_snapshots.py --db .\openbench.db
```

Rollback permanently removes baseline and snapshot rows. Preserve the reported
backup if that data may be needed.

## Restore a backup

Stop all application processes first. Use the exact path printed by the
migration or rollback command. In PowerShell, restore by copying the backup to
the database path after confirming both paths:

```powershell
Copy-Item -LiteralPath .\openbench.db.20261031T000000000000Z.bak -Destination .\openbench.db -Force
```

Replace the example backup filename with the actual generated filename. A
restore replaces the database file, including writes made after the backup, so
confirm the target and preserve a separate copy of the current database first
if it contains newer data.

## Verification

The isolated migration tests use temporary databases to check backup contents,
preservation of existing rows, idempotent retries, foreign-key and angle
constraints, failed-upgrade rollback, and downgrade behavior. They do not modify
the project's database file.
