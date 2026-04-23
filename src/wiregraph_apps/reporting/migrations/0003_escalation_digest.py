import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("wiregraph_reporting", "0002_shadowdecisioncounter"),
        ("wiregraph_tenants", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="EscalationCounter",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("day", models.DateField(help_text="UTC date the escalation fired on.")),
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
                "verbose_name": "Escalation Counter",
                "verbose_name_plural": "Escalation Counters",
                "ordering": ["-created_at"],
                "abstract": False,
                "unique_together": {("tenant", "day")},
            },
        ),
        migrations.AddIndex(
            model_name="escalationcounter",
            index=models.Index(fields=["tenant", "day"], name="wiregraph_r_tenant__esc_idx"),
        ),
        migrations.CreateModel(
            name="AlertDigestEntry",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("day", models.DateField()),
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
                ("asset_name", models.CharField(max_length=64)),
                ("service_domain", models.CharField(blank=True, max_length=255)),
                ("count", models.PositiveIntegerField(default=0)),
                ("first_seen_at", models.DateTimeField()),
                ("last_seen_at", models.DateTimeField()),
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
                "verbose_name": "Alert Digest Entry",
                "verbose_name_plural": "Alert Digest Entries",
                "ordering": ["-created_at"],
                "abstract": False,
                "unique_together": {
                    ("tenant", "day", "outcome", "asset_name", "service_domain"),
                },
            },
        ),
        migrations.AddIndex(
            model_name="alertdigestentry",
            index=models.Index(fields=["tenant", "day"], name="wiregraph_r_tenant__digest_idx"),
        ),
    ]
