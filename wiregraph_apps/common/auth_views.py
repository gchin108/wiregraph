"""JWT auth views with per-endpoint rate limiting.

SimpleJWT's token-obtain and token-refresh endpoints are attractive
brute-force targets. Subclassing here lets us attach a tighter scoped
throttle (``auth``) without affecting the rest of the API.
"""

from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView


class ThrottledTokenObtainPairView(TokenObtainPairView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"


class ThrottledTokenRefreshView(TokenRefreshView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"
