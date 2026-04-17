from django.dispatch import Signal

# Fired when PII is found in a request or response payload.
# Provides: data_event (DataEvent instance), request (HttpRequest)
pii_detected = Signal()

# Fired when a previously unseen PII type is detected for a tenant.
# Provides: data_asset (DataAsset instance), tenant (Tenant instance)
new_data_asset_discovered = Signal()
