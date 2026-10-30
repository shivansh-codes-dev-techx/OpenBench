import sys

from app import models  # noqa: F401
from app.database import Base, engine


def main() -> None:
    try:
        Base.metadata.create_all(bind=engine)
    except Exception as exc:
        print(
            "Database initialization failed. "
            f"Error type: {type(exc).__name__}.",
            file=sys.stderr,
        )
        raise SystemExit(1) from None

    print("Database schema initialized successfully.")


if __name__ == "__main__":
    main()
