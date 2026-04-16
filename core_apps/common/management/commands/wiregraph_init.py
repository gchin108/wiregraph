"""Scaffolder: append a minimal WireGraph configuration block to a settings file.

Run ``python manage.py wiregraph_init --settings-file config/settings.py``.
Appends the bundled INSTALLED_APPS entries, a ``MIDDLEWARE`` guidance block,
and a minimal ``WIREGRAPH = {"ENABLED": True}`` dict. Refuses to overwrite or
duplicate if a ``WIREGRAPH`` block is already present.
"""

from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

TEMPLATE = """
# --- WireGraph configuration (added by `manage.py wiregraph_init`) -----------
import wiregraph

INSTALLED_APPS = [*INSTALLED_APPS, *wiregraph.INSTALLED_APPS]

# Inserts JWTAuthMiddleware + PIIDetectionMiddleware in the correct positions.
MIDDLEWARE = wiregraph.setup(MIDDLEWARE)

WIREGRAPH = {
    "ENABLED": True,
}
# --- end WireGraph configuration ---------------------------------------------
"""


class Command(BaseCommand):
    help = "Append a minimal WireGraph configuration block to a Django settings file."

    def add_arguments(self, parser):
        parser.add_argument(
            "--settings-file",
            required=True,
            help="Path to the Django settings file to modify.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print the block to stdout instead of appending to the file.",
        )

    def handle(self, *args, **options):
        if options["dry_run"]:
            self.stdout.write(TEMPLATE)
            return

        path = Path(options["settings_file"])
        if not path.exists():
            raise CommandError(f"Settings file not found: {path}")

        contents = path.read_text()
        if "WIREGRAPH" in contents:
            raise CommandError(
                f"{path} already contains a WIREGRAPH block — refusing to overwrite. "
                f"Edit the file manually or remove the existing block first."
            )

        with path.open("a") as fp:
            fp.write(TEMPLATE)
        self.stdout.write(f"wiregraph_init: appended WireGraph config block to {path}")
