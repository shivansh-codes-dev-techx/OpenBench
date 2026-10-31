
import app.models  # Register all model tables and foreign-key targets.

from app.database import engine
from app.models.resource_image import ResourceImage


def main():
    ResourceImage.__table__.create(
        bind=engine,
        checkfirst=True,
    )

    print("resource_images table and indexes are ready.")


if __name__ == "__main__":
    main()