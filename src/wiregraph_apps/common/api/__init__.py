"""DRF helpers shared across app api/ packages — gated behind the ``[drf]`` extra."""

from wiregraph._drf import require_drf

require_drf()
