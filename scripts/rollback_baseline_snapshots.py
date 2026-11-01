"""Convenience entry point for the Phase 3B-only SQLite rollback."""

import argparse
from pathlib import Path

from scripts.migrate_baseline_snapshots import downgrade


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    args = parser.parse_args()
    backup = downgrade(args.db.resolve())
    print(f"Phase 3B tables removed; backup: {backup}")


if __name__ == "__main__":
    main()
