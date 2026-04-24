from rest_framework import serializers

from wiregraph_apps.detection.models import AllowlistRule, DataAsset, DataEvent


class DataAssetSerializer(serializers.ModelSerializer):
    class Meta:
        model = DataAsset
        fields = [
            "id",
            "name",
            "label",
            "sensitivity_level",
            "description",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class AllowlistRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = AllowlistRule
        fields = [
            "id",
            "asset_name",
            "endpoint_prefix",
            "reason",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class DataEventSerializer(serializers.ModelSerializer):
    data_asset = serializers.SlugRelatedField(slug_field="name", read_only=True)
    data_asset_label = serializers.CharField(source="data_asset.label", read_only=True)
    external_service_id = serializers.PrimaryKeyRelatedField(
        source="external_service", read_only=True
    )
    external_service_name = serializers.CharField(
        source="external_service.name", read_only=True, default=None
    )
    external_service_domain = serializers.CharField(
        source="external_service.domain", read_only=True, default=None
    )

    class Meta:
        model = DataEvent
        fields = [
            "id",
            "data_asset",
            "data_asset_label",
            "direction",
            "endpoint",
            "method",
            "detection_method",
            "redacted_snippet",
            "confidence",
            "match_count",
            "request_id",
            "timestamp",
            "external_service_id",
            "external_service_name",
            "external_service_domain",
            "outcome",
            "decision_reason",
        ]
        read_only_fields = fields
