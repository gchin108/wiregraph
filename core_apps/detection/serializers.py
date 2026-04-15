from rest_framework import serializers

from core_apps.detection.models import AllowlistRule, DataAsset, DataEvent


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
            "request_id",
            "timestamp",
        ]
        read_only_fields = fields
