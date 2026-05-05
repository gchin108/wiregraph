"""DRF API surface for the detection app — gated behind the ``[drf]`` extra."""

from wiregraph._drf import require_drf

require_drf()
