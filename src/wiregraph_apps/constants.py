DIRECTION_CHOICES = [
    ("inbound", "Inbound"),
    ("outbound", "Outbound"),
    ("wiregraph_egress", "Egress"),
]

DETECTION_METHOD_CHOICES = [
    ("regex", "Regex"),
    ("presidio", "Presidio"),
]

SENSITIVITY_CHOICES = [
    ("low", "Low"),
    ("medium", "Medium"),
    ("high", "High"),
    ("critical", "Critical"),
]

ROLE_CHOICES = [
    ("owner", "Owner"),
    ("admin", "Admin"),
    ("member", "Member"),
]

REDACT_STRATEGY_CHOICES = [
    ("hash", "Hash"),
    ("mask", "Mask"),
    ("truncate", "Truncate"),
]

OUTCOME_CHOICES = [
    ("expected", "Expected"),
    ("acceptable", "Acceptable"),
    ("suspicious", "Suspicious"),
    ("prohibited", "Prohibited"),
]

SINK_CATEGORY_CHOICES = [
    ("payments", "Payments"),
    ("llm", "LLM"),
    ("analytics", "Analytics"),
    ("crm", "CRM"),
    ("email_provider", "Email provider"),
    ("sms", "SMS"),
    ("auth", "Auth"),
    ("logging", "Logging"),
    ("storage", "Storage"),
    ("cdn", "CDN"),
    ("internal", "Internal"),
    ("unknown", "Unknown"),
]

TRUST_TIER_CHOICES = [
    ("trusted", "Trusted"),
    ("known", "Known"),
    ("unknown", "Unknown"),
]

ALLOWLIST_SOURCE_CHOICES = [
    ("manual", "Manual"),
    ("feedback", "Feedback"),
]

# Reasons emitted by detection.classifier.classify().
# Namespaced as "<prefix>:<detail>" so UIs/filters can parse.
# Some reasons are templated with category/asset — see classifier for the exact
# formatting. This tuple contains only static reasons; templated reasons start
# with one of these prefixes:
REASON_PREFIXES = (
    "rule:",
    "category:",
    "policy:",
    "trust:",
    "sensitivity:",
    "flow:",
)

REASONS = (
    "rule:allowlist",
    "policy:pii_to_llm",
    "policy:sensitive_to_llm",
    "policy:sensitive_to_unknown_sink",
    "flow:new_data_flow",
    "sensitivity:low",
    # plus templated reasons — see classifier:
    # "category:<category>_accepts_<asset>"
    # "trust:trusted_sink_category_<category>"
    # "category:<category>_unexpected_<asset>"
)
