"""Framework-agnostic detection core.

Pure-Python contracts and dataclasses shared by Django (and future FastAPI /
other) integrations. Nothing in this package may import ``django``; hosts
bridge core to their stack via adapters (see ``wiregraph_apps.detection.adapters``).
"""
