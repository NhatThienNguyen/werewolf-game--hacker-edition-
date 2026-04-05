"""Card names, vulnerability types, and role definitions."""

from __future__ import annotations

from enum import Enum


class Role(str, Enum):
    WHITE_HAT = "white_hat"
    BLACK_HAT = "black_hat"
    GRAY_HAT = "gray_hat"


# Board vulnerability categories.
VULNERABILITY_TYPES = (
    "Weak password",
    "Untrained Employees",
    "Unpatch systems",
    "Unsanitized input",
    "Unencrypted transmission",
)

# Neutral cards
NEUTRAL_IM_LEARNING = "I'm learning"
NEUTRAL_INSPECT = "Inspect"
NEUTRAL_DIGITAL_FORENSICS = "Digital Forensics"
NEUTRAL_TELL_ME_MORE = "Tell me more"
NEUTRAL_IM_OUT = "I'm out"
NEUTRAL_SHOW_ME = "Show me what you got"
NEUTRAL_ALL_IN = "All in"

NEUTRAL_CARDS = (
    NEUTRAL_IM_LEARNING,
    NEUTRAL_INSPECT,
    NEUTRAL_DIGITAL_FORENSICS,
    NEUTRAL_TELL_ME_MORE,
    NEUTRAL_IM_OUT,
    NEUTRAL_SHOW_ME,
    NEUTRAL_ALL_IN,
)

# Offensive (Black / Gray attack)
OFF_BRUTE_FORCE = "Brute force"
OFF_MANIPULATION = "Manipulation"
OFF_EXPLOITED = "Exploited"
OFF_SQL_INJECTION = "SQL injection"
OFF_MITM = "Man-in-the-middle"
OFF_ZERO_DAYS = "Zero days"

OFFENSIVE_CARDS = (
    OFF_BRUTE_FORCE,
    OFF_MANIPULATION,
    OFF_EXPLOITED,
    OFF_SQL_INJECTION,
    OFF_MITM,
    OFF_ZERO_DAYS,
)

# Defensive (White / Gray resolve)
DEF_MFA = "MFA"
DEF_TRAINING = "Training"
DEF_UPDATE = "Update"
DEF_SANITIZE = "Sanitize input"
DEF_ENCRYPTED = "Encrypted"
DEF_NOT_TODAY = "Not today"

DEFENSIVE_CARDS = (
    DEF_MFA,
    DEF_TRAINING,
    DEF_UPDATE,
    DEF_SANITIZE,
    DEF_ENCRYPTED,
    DEF_NOT_TODAY,
)

# Maps vulnerability <-> attack card <-> defense card
VULN_TO_ATTACK: dict[str, str] = {
    "Weak password": OFF_BRUTE_FORCE,
    "Untrained Employees": OFF_MANIPULATION,
    "Unpatch systems": OFF_EXPLOITED,
    "Unsanitized input": OFF_SQL_INJECTION,
    "Unencrypted transmission": OFF_MITM,
}

VULN_TO_DEFENSE: dict[str, str] = {
    "Weak password": DEF_MFA,
    "Untrained Employees": DEF_TRAINING,
    "Unpatch systems": DEF_UPDATE,
    "Unsanitized input": DEF_SANITIZE,
    "Unencrypted transmission": DEF_ENCRYPTED,
}

ATTACK_TO_VULN = {v: k for k, v in VULN_TO_ATTACK.items()}

MAX_HAND = 6
