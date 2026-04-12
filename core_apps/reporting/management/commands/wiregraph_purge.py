from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Purge expired DataEvent records based on DATA_RETENTION_DAYS setting"

    def handle(self, *args, **options):
        self.stdout.write("wiregraph_purge: Not yet implemented (Week 6)")
