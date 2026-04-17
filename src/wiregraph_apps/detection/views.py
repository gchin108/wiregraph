from django.db.models import Count
from rest_framework import mixins
from rest_framework.response import Response
from rest_framework.views import APIView

from wiregraph_apps.common.tenancy import resolve_tenant
from wiregraph_apps.common.views import TenantScopedViewSet
from wiregraph_apps.detection.allowlist import invalidate_tenant_rules
from wiregraph_apps.detection.models import AllowlistRule, DataAsset, DataEvent
from wiregraph_apps.detection.serializers import (
    AllowlistRuleSerializer,
    DataAssetSerializer,
    DataEventSerializer,
)


class DataEventViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    TenantScopedViewSet,
):
    serializer_class = DataEventSerializer
    queryset = DataEvent.objects.select_related("data_asset").all()

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if direction := params.get("direction"):
            qs = qs.filter(direction=direction)
        if asset := params.get("data_asset"):
            qs = qs.filter(data_asset__name=asset)
        if endpoint := params.get("endpoint"):
            qs = qs.filter(endpoint__icontains=endpoint)
        if ts_gte := params.get("timestamp__gte"):
            qs = qs.filter(timestamp__gte=ts_gte)
        if ts_lte := params.get("timestamp__lte"):
            qs = qs.filter(timestamp__lte=ts_lte)
        return qs.order_by("-timestamp")


class DataAssetViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    TenantScopedViewSet,
):
    serializer_class = DataAssetSerializer
    queryset = DataAsset.objects.all()

    def get_queryset(self):
        return super().get_queryset().order_by("name")


class AllowlistRuleViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
    TenantScopedViewSet,
):
    serializer_class = AllowlistRuleSerializer
    queryset = AllowlistRule.objects.all()

    def get_queryset(self):
        return super().get_queryset().order_by("asset_name", "endpoint_prefix")

    def perform_create(self, serializer):
        tenant = self.get_tenant()
        serializer.save(tenant=tenant)
        invalidate_tenant_rules(tenant)

    def perform_destroy(self, instance):
        tenant = instance.tenant
        instance.delete()
        invalidate_tenant_rules(tenant)


class SummaryStatsView(APIView):
    def get(self, request):
        tenant = resolve_tenant(request)
        if tenant is None:
            return Response({"detail": "No tenant membership."}, status=403)

        events = DataEvent.objects.filter(tenant=tenant)
        return Response(
            {
                "event_count": events.count(),
                "asset_count": DataAsset.objects.filter(tenant=tenant).count(),
                "endpoint_count": events.values("endpoint").distinct().count(),
                "by_direction": dict(
                    events.values_list("direction").annotate(n=Count("id"))
                ),
                "by_asset": dict(
                    events.values_list("data_asset__name").annotate(n=Count("id"))
                ),
            }
        )
