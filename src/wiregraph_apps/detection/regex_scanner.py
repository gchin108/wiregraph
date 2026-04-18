import hashlib
import re
from dataclasses import dataclass
from typing import Iterable

from django.core.exceptions import ImproperlyConfigured

from wiregraph_apps.common.conf import get_custom_patterns, get_redact_strategy


@dataclass(frozen=True)
class Match:
    asset_name: str
    start: int
    end: int
    value: str
    confidence: float


_EMAIL_RE = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
)
_SSN_RE = re.compile(r"\b(?!000|666|9\d{2})\d{3}-(?!00)\d{2}-(?!0000)\d{4}\b")
_CC_RE = re.compile(r"\b(?:\d[ -]?){13,19}\b")
_PHONE_US_RE = re.compile(
    r"(?<!\d)(?:\+?1[\s.-]?)?\(?([2-9]\d{2})\)?[\s.-]?([2-9]\d{2})[\s.-]?(\d{4})(?!\d)",
)
_IPV4_RE = re.compile(
    r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b",
)
_IPV6_RE = re.compile(
    r"(?<![0-9A-Fa-f:])"
    r"(?:[0-9A-Fa-f]{1,4}:){7}[0-9A-Fa-f]{1,4}"
    r"(?![0-9A-Fa-f:])",
)


def _luhn_valid(digits: str) -> bool:
    total = 0
    parity = len(digits) % 2
    for i, ch in enumerate(digits):
        d = ord(ch) - 48
        if i % 2 == parity:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


_FLAG_MAP = {
    "i": re.IGNORECASE,
    "m": re.MULTILINE,
    "s": re.DOTALL,
    "x": re.VERBOSE,
    "a": re.ASCII,
}


def _compile_custom_patterns(specs: list[dict]) -> list[tuple[str, re.Pattern, float]]:
    compiled: list[tuple[str, re.Pattern, float]] = []
    for i, spec in enumerate(specs):
        if not isinstance(spec, dict):
            raise ImproperlyConfigured(
                f"WIREGRAPH.CUSTOM_PATTERNS[{i}] must be a dict, got {type(spec).__name__}"
            )
        name = spec.get("name")
        pattern = spec.get("regex")
        if not name or not isinstance(name, str):
            raise ImproperlyConfigured(
                f"WIREGRAPH.CUSTOM_PATTERNS[{i}] missing 'name'"
            )
        if not pattern or not isinstance(pattern, str):
            raise ImproperlyConfigured(
                f"WIREGRAPH.CUSTOM_PATTERNS[{i}] ({name}) missing 'regex'"
            )
        flags = 0
        for ch in spec.get("flags", "") or "":
            if ch not in _FLAG_MAP:
                raise ImproperlyConfigured(
                    f"WIREGRAPH.CUSTOM_PATTERNS[{i}] ({name}) unknown flag {ch!r}; "
                    f"valid: {''.join(_FLAG_MAP)}"
                )
            flags |= _FLAG_MAP[ch]
        try:
            regex = re.compile(pattern, flags)
        except re.error as e:
            raise ImproperlyConfigured(
                f"WIREGRAPH.CUSTOM_PATTERNS[{i}] ({name}) invalid regex: {e}"
            ) from e
        confidence = float(spec.get("confidence", 0.75))
        compiled.append((name, regex, confidence))
    return compiled


class RegexScanner:
    def __init__(self, custom_patterns: list[dict] | None = None):
        specs = custom_patterns if custom_patterns is not None else get_custom_patterns()
        self._custom = _compile_custom_patterns(specs)

    def scan(self, text: str) -> list[Match]:
        if not text:
            return []
        matches: list[Match] = []
        for m in _EMAIL_RE.finditer(text):
            matches.append(Match("email", m.start(), m.end(), m.group(), 0.99))
        for m in _SSN_RE.finditer(text):
            matches.append(Match("ssn", m.start(), m.end(), m.group(), 0.95))
        for m in _CC_RE.finditer(text):
            raw = m.group()
            digits = re.sub(r"[ -]", "", raw)
            if 13 <= len(digits) <= 19 and _luhn_valid(digits):
                matches.append(Match("credit_card", m.start(), m.end(), raw, 0.9))
        for m in _PHONE_US_RE.finditer(text):
            matches.append(Match("phone_us", m.start(), m.end(), m.group(), 0.85))
        for m in _IPV4_RE.finditer(text):
            matches.append(Match("ipv4", m.start(), m.end(), m.group(), 0.8))
        for m in _IPV6_RE.finditer(text):
            matches.append(Match("ipv6", m.start(), m.end(), m.group(), 0.8))
        for name, regex, confidence in self._custom:
            for m in regex.finditer(text):
                matches.append(Match(name, m.start(), m.end(), m.group(), confidence))
        return matches


def redact(value: str, strategy: str | None = None) -> str:
    strategy = strategy or get_redact_strategy()
    if strategy == "hash":
        return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
    if strategy == "mask":
        if "@" in value:
            local, _, domain = value.partition("@")
            return f"{local[0] if local else ''}***@***{domain[-4:] if len(domain) >= 4 else ''}"
        if len(value) <= 4:
            return "*" * len(value)
        return value[0] + "*" * (len(value) - 2) + value[-1]
    if strategy == "truncate":
        if len(value) <= 6:
            return "***"
        return f"{value[:3]}...{value[-3:]}"
    raise ValueError(f"Unknown redact strategy: {strategy}")


def redact_matches(matches: Iterable[Match], strategy: str | None = None) -> list[str]:
    return [redact(m.value, strategy) for m in matches]
