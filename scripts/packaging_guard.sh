#!/usr/bin/env bash
# Packaging guard for the no-DRF install path.
#
# Catches what the in-process tests/test_no_drf/ suite cannot: a runtime dep
# accidentally left in base [project.dependencies], a namespace-package quirk
# that makes a DRF module importable from disk regardless of sys.modules
# patching, or a conditional import gated on installed package metadata.
#
# Steps:
#   1. Create a clean venv with no DRF on the path.
#   2. ``pip install .`` — base extras only (no [drf]).
#   3. ``manage.py check`` against the no-DRF test settings.
#   4. Import the eagerly-loaded hot-path modules and assert no DRF leaked
#      into ``sys.modules``.
#
# Exit code 0 ⇒ passed. Non-zero ⇒ DRF crept back into the base install.
#
# Run locally with::
#
#   bash scripts/packaging_guard.sh
#
# Or wire into CI as a single step (no second tox column needed).

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV_DIR="${PACKAGING_GUARD_VENV:-$(mktemp -d)/venv}"

echo ">> Creating clean venv at: $VENV_DIR"
python3 -m venv "$VENV_DIR"

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

python -m pip install --upgrade pip >/dev/null

echo ">> Installing wiregraph (no extras) from: $REPO_ROOT"
pip install "$REPO_ROOT" >/dev/null

# Sanity: confirm DRF is genuinely absent in this venv.
if python -c "import rest_framework" 2>/dev/null; then
    echo "FAIL: rest_framework is importable in the clean venv."
    echo "      Check pyproject.toml [project.dependencies] for a stray DRF entry."
    exit 1
fi

echo ">> Running manage.py check against config.settings_no_drf"
cd "$REPO_ROOT"
DJANGO_SETTINGS_MODULE=config.settings_no_drf python manage.py check

echo ">> Importing hot-path modules and asserting no DRF leak"
DJANGO_SETTINGS_MODULE=config.settings_no_drf python -c "
import sys
import django
django.setup()
import wiregraph_apps.detection.middleware  # noqa: F401
import wiregraph_apps.egress.interceptor  # noqa: F401
import wiregraph_apps.detection.persistence  # noqa: F401
import wiregraph_apps.detection.pipeline  # noqa: F401
import wiregraph_apps.common.admin_views  # noqa: F401
leaked = sorted(
    n for n in sys.modules
    if n.split('.')[0] in ('rest_framework', 'drf_spectacular')
)
assert not leaked, f'DRF modules leaked: {leaked}'
print('OK — no DRF imports in hot-path modules')
"

echo ">> packaging guard PASSED"
