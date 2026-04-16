"""Tests for the ``wiregraph_init`` management command."""

from io import StringIO

import pytest
from django.core.management import CommandError, call_command


def _call(**kwargs):
    out = StringIO()
    call_command("wiregraph_init", stdout=out, **kwargs)
    return out.getvalue()


def test_dry_run_prints_template_to_stdout():
    output = _call(dry_run=True, settings_file="/nonexistent/path.py")
    assert "import wiregraph" in output
    assert 'WIREGRAPH = {' in output
    assert '"ENABLED": True' in output


def test_missing_file_raises(tmp_path):
    missing = tmp_path / "does_not_exist.py"
    with pytest.raises(CommandError, match="not found"):
        call_command("wiregraph_init", settings_file=str(missing))


def test_appends_block_to_settings_file(tmp_path):
    settings_file = tmp_path / "settings.py"
    settings_file.write_text("INSTALLED_APPS = []\nMIDDLEWARE = []\n")

    output = _call(settings_file=str(settings_file))

    contents = settings_file.read_text()
    assert "WIREGRAPH" in contents
    assert "wiregraph.setup(MIDDLEWARE)" in contents
    assert str(settings_file) in output


def test_refuses_to_duplicate_block(tmp_path):
    settings_file = tmp_path / "settings.py"
    settings_file.write_text("WIREGRAPH = {}\n")

    with pytest.raises(CommandError, match="already contains a WIREGRAPH block"):
        call_command("wiregraph_init", settings_file=str(settings_file))
