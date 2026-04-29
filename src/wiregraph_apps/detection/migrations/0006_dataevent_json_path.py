from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("wiregraph_detection", "0005_dataevent_shadow_alert_level"),
    ]

    operations = [
        migrations.AddField(
            model_name="dataevent",
            name="json_path",
            field=models.CharField(
                max_length=512,
                blank=True,
                help_text="Dotted path to the JSON field containing the match, e.g. 'body.messages[0].content'.",
            ),
        ),
    ]
