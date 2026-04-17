DIRECTION_CHOICES = [
    ("inbound", "Inbound"),
    ("outbound", "Outbound"),
    ("egress", "Egress"),
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
