"""Optional Celery integration for retention purging.

If Celery is installed, importing this module registers the
``wiregraph.celery.purge_expired_events`` task via ``@shared_task``. Consumers
schedule it by merging the result of :func:`schedule` into their
``CELERY_BEAT_SCHEDULE``:

    from celery.schedules import crontab
    import wiregraph.celery as wg_celery

    CELERY_BEAT_SCHEDULE = {
        **wg_celery.schedule(hour=3, minute=0),
        # ... your other scheduled tasks ...
    }

If Celery is not installed the task is not registered and :func:`schedule`
raises ``RuntimeError``; the plain ``wiregraph_purge`` management command is
unaffected and remains available via cron/systemd.
"""

from __future__ import annotations

from typing import Any

from wiregraph_apps.reporting.purge import purge_expired_events as _purge_core

TASK_NAME = "wiregraph.celery.purge_expired_events"

try:
    from celery import shared_task
    from celery.schedules import crontab

    _CELERY_AVAILABLE = True
except ImportError:  # pragma: no cover — exercised via test monkey-patch
    _CELERY_AVAILABLE = False


if _CELERY_AVAILABLE:

    @shared_task(name=TASK_NAME)
    def purge_expired_events(
        dry_run: bool = False,
        batch_size: int = 1000,
        retention_days: int | None = None,
    ) -> dict[str, Any]:
        result = _purge_core(
            dry_run=dry_run,
            batch_size=batch_size,
            retention_days=retention_days,
        )
        return {
            "cutoff_iso": result.cutoff_iso,
            "candidates": result.candidates,
            "deleted": result.deleted,
            "dry_run": result.dry_run,
        }


def schedule(hour: int = 3, minute: int = 0) -> dict[str, dict[str, Any]]:
    """Return a ``CELERY_BEAT_SCHEDULE`` fragment that runs the purge daily."""
    if not _CELERY_AVAILABLE:
        raise RuntimeError(
            "wiregraph.celery.schedule() requires Celery. "
            "Install with `pip install celery` or use the wiregraph_purge "
            "management command directly."
        )
    return {
        "wiregraph-purge": {
            "task": TASK_NAME,
            "schedule": crontab(hour=hour, minute=minute),
        },
    }
