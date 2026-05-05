"""DRF API surface for the reporting app — gated behind the ``[drf]`` extra."""

from wiregraph._drf import require_drf

require_drf()
