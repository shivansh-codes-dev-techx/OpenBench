import os


# Keep pytest independent from developer or production environment files.
os.environ["SECRET_KEY"] = "openbench-test-only-secret-not-for-production"
