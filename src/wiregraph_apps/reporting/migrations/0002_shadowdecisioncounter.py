import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("wiregraph_reporting", "0001_initial"),
        ("wiregraph_tenants", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="ShadowDecisionCounter",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("day", models.DateField(help_text="UTC date the classified event belongs to.")),
                (
                    "outcome",
                    models.CharField(
                        choices=[
                            ("expected", "Expected"),
                            ("acceptable", "Acceptable"),
                            ("suspicious", "Suspicious"),
                            ("prohibited", "Prohibited"),
                        ],
                        max_length=20,
                    ),
                ),
                (
                    "shadow_alert_level",
                    models.CharField(
                        choices=[
                            ("expected", "Expected"),
                            ("acceptable", "Acceptable"),
                            ("suspicious", "Suspicious"),
                            ("prohibited", "Prohibited"),
                        ],
                        max_length=20,
                    ),
                ),
                ("count", models.PositiveIntegerField(default=0)),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="%(class)s_set",
                        to="wiregraph_tenants.tenant",
                    ),
                ),
            ],
            options={
                "verbose_name": "Shadow Decision Counter",
                "verbose_name_plural": "Shadow Decision Counters",
                "ordering": ["-created_at"],
                "abstract": False,
                "unique_together": {("tenant", "day", "outcome", "shadow_alert_level")},
            },
        ),
        migrations.AddIndex(
            model_name="shadowdecisioncounter",
            index=models.Index(fields=["tenant", "day"], name="wiregraph_r_tenant__shadow_idx"),
        ),
    ]
