from django.core.management.base import BaseCommand

from wiregraph_apps.reporting.purge import DEFAULT_BATCH_SIZE, purge_expired_events


class Command(BaseCommand):
    help = "Purge expired DataEvent records based on DATA_RETENTION_DAYS setting"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report how many rows would be deleted without deleting them.",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=DEFAULT_BATCH_SIZE,
            help=f"Delete batch size (default: {DEFAULT_BATCH_SIZE}).",
        )
        parser.add_argument(
            "--retention-days",
            type=int,
            default=None,
            help="Override WIREGRAPH['DATA_RETENTION_DAYS'] for this run.",
        )

    def handle(self, *args, **options):
        result = purge_expired_events(
            dry_run=options["dry_run"],
            batch_size=options["batch_size"],
            retention_days=options["retention_days"],
        )
        verb = "would delete" if result.dry_run else "deleted"
        self.stdout.write(
            f"wiregraph_purge: {verb} {result.candidates if result.dry_run else result.deleted} "
            f"DataEvent row(s) older than {result.cutoff_iso}"
        )
