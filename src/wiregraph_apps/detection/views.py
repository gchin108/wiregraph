from django.db.models import Count
from rest_framework import mixins
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ViewSet

from wiregraph_apps.common.tenancy import resolve_tenant
from wiregraph_apps.common.views import TenantScopedMixin, TenantScopedViewSet
from wiregraph_apps.detection.allowlist import invalidate_tenant_rules
from wiregraph_apps.detection.models import AllowlistRule, DataAsset, DataEvent
from wiregraph_apps.detection.selectors import (
    endpoint_node_events,
    event_trace,
    get_endpoint_node,
    list_endpoint_nodes,
)
from wiregraph_apps.detection.serializers import (
    AllowlistRuleSerializer,
    DataAssetSerializer,
    DataEventSerializer,
    EndpointNodeSerializer,
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

    @action(detail=True, methods=["get"])
    def trace(self, request, pk=None):
        trace = event_trace(self.get_tenant(), pk)
        if trace is None:
            return Response({"detail": "Not found."}, status=404)
        return Response(
            {
                "inbound": DataEventSerializer(trace.inbound, many=True).data,
                "outbound": (
                    DataEventSerializer(trace.outbound).data
                    if trace.outbound is not None
                    else None
                ),
                "asset": DataAssetSerializer(trace.asset).data,
            }
        )


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


class EndpointNodeViewSet(TenantScopedMixin, ViewSet):
    """Aggregated outbound endpoints — one node per (service, endpoint, method)."""

    queryset = DataEvent.objects.none()  # tenancy mixin guard

    def list(self, request):
        nodes = list_endpoint_nodes(self.get_tenant())
        return Response(EndpointNodeSerializer(nodes, many=True).data)

    def retrieve(self, request, pk=None):
        node = get_endpoint_node(self.get_tenant(), pk)
        if node is None:
            return Response({"detail": "Not found."}, status=404)
        return Response(EndpointNodeSerializer(node).data)

    @action(detail=True, methods=["get"])
    def events(self, request, pk=None):
        tenant = self.get_tenant()
        if get_endpoint_node(tenant, pk) is None:
            return Response({"detail": "Not found."}, status=404)
        qs = endpoint_node_events(tenant, pk)
        paginator = self.paginator
        page = paginator.paginate_queryset(qs, request, view=self) if paginator else None
        serializer = DataEventSerializer(page if page is not None else qs, many=True)
        if page is not None:
            return paginator.get_paginated_response(serializer.data)
        return Response(serializer.data)

    @property
    def paginator(self):
        if not hasattr(self, "_paginator"):
            from rest_framework.settings import api_settings

            cls = api_settings.DEFAULT_PAGINATION_CLASS
            self._paginator = cls() if cls else None
        return self._paginator


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
