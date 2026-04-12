from django.dispatch import Signal

# Fired when PII is detected in an outbound HTTP call to a third-party service.
# Provides: data_event (DataEvent instance), external_service (ExternalService instance)
egress_pii_leak = Signal()
