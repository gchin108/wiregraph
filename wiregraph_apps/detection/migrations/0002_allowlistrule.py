import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("wiregraph_detection", "0001_initial"),
        ("wiregraph_tenants", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="AllowlistRule",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "asset_name",
                    models.CharField(
                        help_text="DataAsset.name to suppress, e.g. 'email'. Must match a detector asset name.",
                        max_length=255,
                    ),
                ),
                (
                    "endpoint_prefix",
                    models.CharField(
                        blank=True,
                        help_text="Optional endpoint path prefix. Empty string matches all endpoints.",
                        max_length=2048,
                    ),
                ),
                (
                    "reason",
                    models.CharField(
                        blank=True,
                        help_text="Human-readable rationale, e.g. 'Login form — email is expected'.",
                        max_length=255,
                    ),
                ),
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
                "verbose_name": "Allowlist Rule",
                "verbose_name_plural": "Allowlist Rules",
                "ordering": ["-created_at"],
                "abstract": False,
                "unique_together": {("tenant", "asset_name", "endpoint_prefix")},
                "indexes": [
                    models.Index(fields=["tenant", "asset_name"], name="detection_a_tenant__ff7255_idx"),
                ],
            },
        ),
    ]
