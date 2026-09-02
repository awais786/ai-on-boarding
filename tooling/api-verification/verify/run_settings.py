"""Settings for the verification run.

Imports the project's settings unchanged and overrides one thing: where the
database file lives, so a run never writes over a database the developer is
using. Nothing about the application's behaviour changes - the code under
verification is the code as shipped, reached over HTTP.

Delivery is pointed at the mail catcher through the RESET_SMTP_* environment
variables the project's settings already read, so that path needs no override
here.
"""
from pathlib import Path

from sdd_django_demo.settings import *  # noqa: F401,F403

BUILD_DIR = Path(__file__).resolve().parent.parent / "build"
BUILD_DIR.mkdir(exist_ok=True)

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BUILD_DIR / "verification.sqlite3",
    }
}
