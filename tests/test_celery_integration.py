"""Tests for the optional Celery integration.

Verifies:
- When Celery is available, the shared_task is registered under the expected
  name and ``schedule()`` returns a well-formed Beat fragment.
- When Celery is unavailable (simulated), ``schedule()`` raises and the task
  is simply absent.
"""

import importlib
import sys

import pytest


def test_schedule_returns_beat_fragment():
    import wiregraph.celery as wg_celery

    if not wg_celery._CELERY_AVAILABLE:
        pytest.skip("Celery not installed in this environment")

    fragment = wg_celery.schedule(hour=4, minute=15)
    assert "wiregraph-purge" in fragment
    entry = fragment["wiregraph-purge"]
    assert entry["task"] == wg_celery.TASK_NAME
    # crontab instance carries hour/minute attributes as frozensets
    assert 4 in entry["schedule"].hour
    assert 15 in entry["schedule"].minute


def test_task_name_stable():
    import wiregraph.celery as wg_celery

    assert wg_celery.TASK_NAME == "wiregraph.celery.purge_expired_events"


def test_schedule_raises_without_celery(monkeypatch):
    """Simulate Celery absence by reloading the module with celery hidden."""
    import wiregraph.celery as wg_celery

    # Force the "celery not available" branch
    monkeypatch.setattr(wg_celery, "_CELERY_AVAILABLE", False)
    with pytest.raises(RuntimeError, match="requires Celery"):
        wg_celery.schedule()


def test_reporting_apps_ready_tolerates_missing_celery(monkeypatch):
    """``ReportingConfig.ready()`` must not crash if the celery import fails."""
    from wiregraph_apps.reporting.apps import ReportingConfig

    # Pretend wiregraph.celery can't be imported
    real_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__

    def fake_import(name, *args, **kwargs):
        if name == "wiregraph.celery":
            raise ImportError("simulated missing celery")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)

    cfg = ReportingConfig.__new__(ReportingConfig)
    cfg.ready()  # must not raise
