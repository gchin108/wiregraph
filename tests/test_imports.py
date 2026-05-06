"""Regression guard: hot-path modules must not transitively import DRF.

The detection middleware and egress interceptor are eagerly imported on every
request handled by a wiregraph-instrumented project. They must work in a
no-DRF install (``pip install wiregraph`` without the ``[drf]`` extra), so
their module-load graph must not pull in ``rest_framework``,
``rest_framework_simplejwt``, or ``drf_spectacular``.

Implementation: spawn a fresh interpreter with a ``sys.meta_path`` finder
that raises on any DRF-namespaced import, then ``django.setup()`` against
``config.settings_no_drf`` and import the hot-path modules. If anything
under the DRF namespace gets imported during module load, the subprocess
exits non-zero. This catches what in-process ``sys.modules`` patching
cannot — module load order has already happened by the time our test runs.
"""

from __future__ import annotations

import subprocess
import sys


_HOT_PATH_MODULES = [
    "wiregraph_apps.detection.middleware",
    "wiregraph_apps.egress.interceptor",
    "wiregraph_apps.detection.persistence",
    "wiregraph_apps.detection.pipeline",
    "wiregraph_apps.common.admin_views",
]


_HARNESS = '''\
import sys

_BLOCKED_PREFIXES = ("rest_framework", "drf_spectacular")

class _DRFBlocker:
    def find_spec(self, name, path=None, target=None):
        if name.split(".")[0] in _BLOCKED_PREFIXES:
            raise ImportError(
                f"DRF blocked by test_imports regression guard: {name}"
            )
        return None

sys.meta_path.insert(0, _DRFBlocker())

import os
os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings_no_drf"

import django
django.setup()

__IMPORTS__

leaked = sorted(
    n for n in sys.modules if n.split(".")[0] in _BLOCKED_PREFIXES
)
assert not leaked, f"DRF modules leaked into sys.modules: {leaked}"
'''


def _run_subprocess(modules: list[str]) -> subprocess.CompletedProcess:
    imports = "\n".join(f"import {m}" for m in modules)
    code = _HARNESS.replace("__IMPORTS__", imports)
    return subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
    )


def test_hot_path_modules_do_not_import_drf():
    result = _run_subprocess(_HOT_PATH_MODULES)
    assert result.returncode == 0, (
        f"Hot-path module load pulled in DRF.\n"
        f"--- stdout ---\n{result.stdout}\n"
        f"--- stderr ---\n{result.stderr}"
    )


def test_doctor_command_module_does_not_import_drf():
    # The doctor command's _check_api_extra path is allowed to call
    # drf_available() (which catches ImportError), so importing the command
    # module itself must stay DRF-free.
    result = _run_subprocess(
        ["wiregraph_apps.common.management.commands.wiregraph_doctor"]
    )
    assert result.returncode == 0, (
        f"wiregraph_doctor module load pulled in DRF.\n"
        f"--- stdout ---\n{result.stdout}\n"
        f"--- stderr ---\n{result.stderr}"
    )
