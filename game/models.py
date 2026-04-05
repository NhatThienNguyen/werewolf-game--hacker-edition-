"""Serializable game state pieces."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .constants import Role


class Phase(str, Enum):
    GAME_OVER = "game_over"
    DAY_DRAW = "day_draw"
    DAY_INSPECT = "day_inspect"
    DAY_NEUTRAL = "day_neutral"
    DAY_DISCUSSION = "day_discussion"
    DAY_VOTE = "day_vote"
    NIGHT_BLACK = "night_black"
    NIGHT_WHITE = "night_white"
    NIGHT_GRAY = "night_gray"


@dataclass
class Vulnerability:
    vid: int
    kind: str
    # hidden | known (discovered) | resolved | exploited
    status: str = "hidden"
    discovered_by: int | None = None
    public: bool = False

    def to_public(self) -> dict[str, Any]:
        return {
            "id": self.vid,
            "kind": self.kind if self.public or self.status != "hidden" else "?",
            "status": self.status,
            "public": self.public,
        }


@dataclass
class Player:
    pid: int
    name: str
    role: Role
    hand: list[str] = field(default_factory=list)
    is_human: bool = False
    eliminated: bool = False
    # Times targeted by a successful elimination vote (for card penalty scaling).
    elimination_votes_survived: int = 0
    skip_next_turn: bool = False
    all_in_active: bool = False
    im_out_next_card_bonus: bool = False

    def hand_size(self) -> int:
        return len(self.hand)


@dataclass
class PendingAttack:
    attacker_id: int
    target_vuln_id: int
    card_used: str
    wrong_vulnerability: bool


@dataclass
class GameConfig:
    player_count: int
    human_name: str = "You"

