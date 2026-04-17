import wiregraph
from wiregraph import apps


def test_installed_apps_constant_is_dependency_ordered():
    expected = [
        "wiregraph_apps.common",
        "wiregraph_apps.tenants",
        "wiregraph_apps.detection",
        "wiregraph_apps.egress",
        "wiregraph_apps.reporting",
    ]
    assert apps.INSTALLED_APPS == expected


def test_installed_apps_reexported_on_package():
    assert wiregraph.INSTALLED_APPS == apps.INSTALLED_APPS


def test_common_and_tenants_precede_dependents():
    idx = {name: i for i, name in enumerate(wiregraph.INSTALLED_APPS)}
    assert idx["wiregraph_apps.common"] < idx["wiregraph_apps.detection"]
    assert idx["wiregraph_apps.common"] < idx["wiregraph_apps.egress"]
    assert idx["wiregraph_apps.tenants"] < idx["wiregraph_apps.detection"]
    assert idx["wiregraph_apps.tenants"] < idx["wiregraph_apps.egress"]
