"""Framework-agnostic detection core.

Pure-Python contracts and dataclasses shared by Django (and future FastAPI /
other) integrations. Nothing in this package may import ``django`` — the
ring-1 extraction plan tracks the modules that still need to move.
"""
