from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("wiregraph_detection", "0006_dataevent_json_path"),
    ]

    operations = [
        migrations.AddField(
            model_name="dataevent",
            name="allowlist_rule",
            field=models.ForeignKey(
                blank=True,
                help_text="Allowlist rule that classified this event as 'expected', if any.",
                null=True,
                on_delete=models.deletion.SET_NULL,
                related_name="data_events",
                to="wiregraph_detection.allowlistrule",
            ),
        ),
    ]
