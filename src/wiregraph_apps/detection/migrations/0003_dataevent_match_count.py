from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("wiregraph_detection", "0002_allowlistrule"),
    ]

    operations = [
        migrations.AddField(
            model_name="dataevent",
            name="match_count",
            field=models.PositiveIntegerField(
                default=1,
                help_text="Number of matches coalesced into this event (per asset per request)",
            ),
        ),
    ]
