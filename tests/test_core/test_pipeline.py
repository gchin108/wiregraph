"""Framework-agnostic tests for :mod:`wiregraph_core.pipeline`.

Use fakes for the sink and scanner — no Django, no ORM, no settings.
These tests prove the orchestrator can drive a non-Django host without
modification.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Iterable

from wiregraph_core.pipeline import enrich_with_json_path, run_pipeline
from wiregraph_core.types import Match


@dataclass
class FakeSink:
    persist_calls: list[dict] = field(default_factory=list)
    egress_calls: list[dict] = field(default_factory=list)
    persist_return: list[Any] = field(default_factory=lambda: ["row"])
    egress_return: list[Any] = field(default_factory=lambda: ["egress-row"])

    def persist_matches(self, **kwargs: Any) -> list[Any]:
        kwargs["matches"] = list(kwargs["matches"])
        self.persist_calls.append(kwargs)
        return self.persist_return

    def persist_egress_matches(self, **kwargs: Any) -> list[Any]:
        kwargs["matches"] = list(kwargs["matches"])
        self.egress_calls.append(kwargs)
        return self.egress_return


@dataclass
class FakeScanner:
    matches: list[Match]

    def scan(self, text: str) -> list[Match]:
        return list(self.matches)


def _email_match(value: str = "a@b.com") -> Match:
    return Match(asset_name="email", start=0, end=len(value), value=value, confidence=0.99)


def test_no_tenant_returns_empty_and_skips_everything():
    sink = FakeSink()
    scanner = FakeScanner([_email_match()])
    enqueue_calls: list[dict] = []

    out = run_pipeline(
        scanner=scanner,
        sink=sink,
        presidio_enqueue=lambda **kw: enqueue_calls.append(kw),
        tenant=None,
        text="hello a@b.com",
        direction="inbound",
        endpoint="/x",
        method="POST",
    )

    assert out == []
    assert sink.persist_calls == []
    assert sink.egress_calls == []
    assert enqueue_calls == []


def test_empty_text_returns_empty_and_skips_everything():
    sink = FakeSink()
    scanner = FakeScanner([_email_match()])
    enqueue_calls: list[dict] = []

    out = run_pipeline(
        scanner=scanner,
        sink=sink,
        presidio_enqueue=lambda **kw: enqueue_calls.append(kw),
        tenant=object(),
        text="",
        direction="inbound",
        endpoint="/x",
        method="POST",
    )

    assert out == []
    assert sink.persist_calls == []
    assert enqueue_calls == []


def test_inbound_match_goes_to_persist_matches_with_detection_method_regex():
    sink = FakeSink()
    scanner = FakeScanner([_email_match()])
    tenant = object()

    out = run_pipeline(
        scanner=scanner,
        sink=sink,
        presidio_enqueue=None,
        tenant=tenant,
        text="hello a@b.com",
        direction="inbound",
        endpoint="/x",
        method="POST",
        request_id="req-1",
    )

    assert out == ["row"]
    assert len(sink.persist_calls) == 1
    call = sink.persist_calls[0]
    assert call["tenant"] is tenant
    assert call["direction"] == "inbound"
    assert call["detection_method"] == "regex"
    assert call["request_id"] == "req-1"
    assert sink.egress_calls == []


def test_egress_match_goes_to_persist_egress_matches():
    sink = FakeSink()
    scanner = FakeScanner([_email_match()])

    out = run_pipeline(
        scanner=scanner,
        sink=sink,
        tenant=object(),
        text="hello a@b.com",
        direction="egress",
        endpoint="/v1/chat",
        method="POST",
    )

    assert out == ["egress-row"]
    assert sink.persist_calls == []
    assert len(sink.egress_calls) == 1


def test_egress_json_enriches_matches_with_json_path():
    sink = FakeSink()
    scanner = FakeScanner([_email_match("user@example.com")])
    body = json.dumps({"user": {"contact": "user@example.com"}})

    run_pipeline(
        scanner=scanner,
        sink=sink,
        tenant=object(),
        text=body,
        direction="egress",
        endpoint="/v1/x",
        method="POST",
        content_type="application/json; charset=utf-8",
    )

    persisted = sink.egress_calls[0]["matches"]
    assert len(persisted) == 1
    assert persisted[0].json_path == "body.user.contact"


def test_no_matches_still_enqueues_presidio():
    sink = FakeSink()
    scanner = FakeScanner([])
    enqueue_calls: list[dict] = []

    run_pipeline(
        scanner=scanner,
        sink=sink,
        presidio_enqueue=lambda **kw: enqueue_calls.append(kw),
        tenant=object(),
        text="no pii here",
        direction="inbound",
        endpoint="/x",
        method="GET",
    )

    assert sink.persist_calls == []
    assert sink.egress_calls == []
    assert len(enqueue_calls) == 1
    assert enqueue_calls[0]["direction"] == "inbound"


def test_external_service_pk_threaded_to_presidio_enqueue():
    sink = FakeSink()
    scanner = FakeScanner([])
    enqueue_calls: list[dict] = []

    class _Svc:
        pk = 42

    run_pipeline(
        scanner=scanner,
        sink=sink,
        presidio_enqueue=lambda **kw: enqueue_calls.append(kw),
        tenant=object(),
        text="hello",
        direction="egress",
        endpoint="/x",
        method="POST",
        external_service=_Svc(),
    )

    assert enqueue_calls[0]["external_service_id"] == 42


def test_enrich_with_json_path_returns_original_on_parse_failure():
    matches = [_email_match()]
    out = enrich_with_json_path(matches, "not json {")
    assert out == matches


def test_enrich_with_json_path_handles_arrays():
    parsed = json.dumps({"items": [{"email": "a@b.com"}, {"email": "c@d.com"}]})
    matches = [_email_match("c@d.com")]
    out = enrich_with_json_path(matches, parsed)
    assert out[0].json_path == "body.items[1].email"
