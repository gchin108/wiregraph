from rest_framework import serializers

from wiregraph_apps.detection.models import AllowlistRule, DataAsset, DataEvent


class AssetCountSerializer(serializers.Serializer):
    name = serializers.CharField()
    label = serializers.CharField()
    count = serializers.IntegerField()


class HourBucketSerializer(serializers.Serializer):
    hour = serializers.DateTimeField()
    count = serializers.IntegerField()


class EndpointNodeSerializer(serializers.Serializer):
    id = serializers.CharField()
    external_service_id = serializers.CharField(allow_null=True)
    external_service_name = serializers.CharField(allow_null=True)
    external_service_domain = serializers.CharField(allow_null=True)
    endpoint = serializers.CharField()
    method = serializers.CharField()
    direction = serializers.CharField()
    worst_outcome = serializers.CharField()
    event_count = serializers.IntegerField()
    last_seen = serializers.DateTimeField()
    first_seen = serializers.DateTimeField()
    assets = AssetCountSerializer(many=True)
    sparkline = HourBucketSerializer(many=True)


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
            "domain",
            "domain_suffix",
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
            "json_path",
            "confidence",
            "match_count",
            "request_id",
            "timestamp",
            "external_service_id",
            "external_service_name",
            "external_service_domain",
            "outcome",
            "decision_reason",
            "allowlist_rule",
        ]
        read_only_fields = fields
