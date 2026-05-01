import factory
from django.contrib.auth import get_user_model

from wiregraph_apps.detection.models import DataAsset, DataEvent
from wiregraph_apps.egress.models import ExternalService
from wiregraph_apps.tenants.models import Tenant, TenantMembership


class TenantFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Tenant

    name = factory.Sequence(lambda n: f"Tenant {n}")
    slug = factory.Sequence(lambda n: f"tenant-{n}")


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = get_user_model()

    username = factory.Sequence(lambda n: f"user{n}")
    email = factory.Sequence(lambda n: f"user{n}@example.com")
    password = factory.PostGenerationMethodCall("set_password", "pw")


class TenantMembershipFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = TenantMembership

    tenant = factory.SubFactory(TenantFactory)
    user = factory.SubFactory(UserFactory)
    role = "member"


class DataAssetFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = DataAsset

    tenant = factory.SubFactory(TenantFactory)
    name = factory.Sequence(lambda n: f"asset_{n}")
    label = factory.LazyAttribute(lambda o: o.name.replace("_", " ").title())
    sensitivity_level = "medium"


class ExternalServiceFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ExternalService

    tenant = factory.SubFactory(TenantFactory)
    domain = factory.Sequence(lambda n: f"svc{n}.example.com")
    name = factory.LazyAttribute(lambda o: o.domain)
    first_seen_at = factory.LazyFunction(lambda: __import__("django.utils.timezone", fromlist=["now"]).now())
    last_seen_at = factory.LazyFunction(lambda: __import__("django.utils.timezone", fromlist=["now"]).now())


class DataEventFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = DataEvent

    tenant = factory.SubFactory(TenantFactory)
    data_asset = factory.SubFactory(DataAssetFactory, tenant=factory.SelfAttribute("..tenant"))
    direction = "inbound"
    endpoint = "/api/test/"
    method = "POST"
    detection_method = "regex"
    redacted_snippet = "sha256:deadbeef"
    confidence = 0.95
    request_id = "test-req"
    timestamp = factory.LazyFunction(lambda: __import__("django.utils.timezone", fromlist=["now"]).now())
