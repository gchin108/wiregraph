import wiregraph
from wiregraph import apps


def test_installed_apps_constant_is_dependency_ordered():
    expected = [
        "core_apps.common",
        "core_apps.tenants",
        "core_apps.detection",
        "core_apps.egress",
        "core_apps.reporting",
    ]
    assert apps.INSTALLED_APPS == expected


def test_installed_apps_reexported_on_package():
    assert wiregraph.INSTALLED_APPS == apps.INSTALLED_APPS


def test_common_and_tenants_precede_dependents():
    idx = {name: i for i, name in enumerate(wiregraph.INSTALLED_APPS)}
    assert idx["core_apps.common"] < idx["core_apps.detection"]
    assert idx["core_apps.common"] < idx["core_apps.egress"]
    assert idx["core_apps.tenants"] < idx["core_apps.detection"]
    assert idx["core_apps.tenants"] < idx["core_apps.egress"]
