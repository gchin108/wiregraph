from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("wiregraph_detection", "0004_rename_detection_a_tenant__ff7255_idx_wiregraph_d_tenant__bf9538_idx_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="dataevent",
            name="shadow_alert_level",
            field=models.CharField(
                max_length=20,
                blank=True,
                default="",
                choices=[
                    ("expected", "Expected"),
                    ("acceptable", "Acceptable"),
                    ("suspicious", "Suspicious"),
                    ("prohibited", "Prohibited"),
                ],
                help_text="Phase 2 shadow: level receivers *would* dispatch at under the new policy.",
            ),
        ),
    ]
