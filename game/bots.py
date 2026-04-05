"""Simple bot policy: legal random moves until the human must act."""

from __future__ import annotations

import random
from typing import Any

from .constants import (
    NEUTRAL_CARDS,
    NEUTRAL_DIGITAL_FORENSICS,
    NEUTRAL_INSPECT,
    OFFENSIVE_CARDS,
    OFF_ZERO_DAYS,
    Role,
    VULN_TO_ATTACK,
    VULN_TO_DEFENSE,
)
from .engine import WerewolfGame
from .models import Phase


def _pick_discard_indices(hand_len: int, need: int, rng: random.Random) -> list[int]:
    idx = list(range(hand_len))
    rng.shuffle(idx)
    return sorted(idx[:need], reverse=True)


def _neutral_turn_pid(game: WerewolfGame) -> int | None:
    if game.phase != Phase.DAY_NEUTRAL:
        return None
    if game.neutral_index >= len(game.neutral_order):
        return None
    return game.neutral_order[game.neutral_index]


def choose_bot_action(game: WerewolfGame, human_pid: int) -> tuple[int, dict[str, Any]] | None:
    """Return (player_id, action) for the next bot move, or None if human should act."""
    rng = game.rng

    if game.phase == Phase.GAME_OVER:
        return None

    for pid, need in game.needs_discard:
        if pid == human_pid:
            return None
        pl = game.players[pid]
        return pid, {"type": "discard_down", "indices": _pick_discard_indices(len(pl.hand), need, rng)}

    if game.phase == Phase.DAY_INSPECT and game.company_must_choose_inspector:
        company = next(p for p in game.players if p.role == Role.COMPANY and not p.eliminated)
        if company.pid == human_pid:
            return None
        pick = rng.choice(game.inspect_candidates)
        return company.pid, {"type": "company_pick_inspector", "target_pid": pick}

    if game.phase == Phase.DAY_DISCUSSION and game.company_may_forensics:
        company = next(p for p in game.players if p.role == Role.COMPANY and not p.eliminated)
        if company.pid != human_pid and NEUTRAL_DIGITAL_FORENSICS in company.hand:
            return company.pid, {"type": "forensics"}

    nt = _neutral_turn_pid(game)
    if nt is not None:
        pid = nt
        if pid == human_pid:
            return None
        pl = game.players[pid]
        neutrals = [c for c in pl.hand if c in NEUTRAL_CARDS]
        if neutrals and rng.random() < 0.35:
            card = rng.choice(neutrals)
            act: dict[str, Any] = {"type": "neutral_play", "card": card}
            if card == "Show me what you got":
                others = [p.pid for p in game.living_players() if p.pid != pid]
                if others:
                    act["target_pid"] = rng.choice(others)
            return pid, act
        return pid, {"type": "neutral_pass"}

    if game.phase == Phase.DAY_VOTE and game.vote_active:
        if game.votes_cast.get(human_pid) is None and human_pid in game.votes_cast:
            return None
        for pid, v in game.votes_cast.items():
            if v is not None or pid == human_pid:
                continue
            living = [p.pid for p in game.living_players()]
            return pid, {"type": "vote", "target_pid": rng.choice(living)}

    if game.phase == Phase.NIGHT_BLACK and game.night_black_actor is not None:
        pid = game.night_black_actor
        if pid == human_pid:
            return None
        pl = game.players[pid]
        hidden = [v for v in game.vulnerabilities if v.status in ("hidden", "known")]
        attacks = [c for c in pl.hand if c in OFFENSIVE_CARDS]
        if NEUTRAL_INSPECT in pl.hand and rng.random() < 0.25:
            return pid, {"type": "night_black", "mode": "inspect"}
        if attacks and hidden and rng.random() < 0.7:
            vuln = rng.choice(hidden)
            expected = VULN_TO_ATTACK.get(vuln.kind)
            if expected in pl.hand:
                card = expected
            elif OFF_ZERO_DAYS in pl.hand and rng.random() < 0.35:
                card = OFF_ZERO_DAYS
            else:
                card = rng.choice(attacks)
            return pid, {"type": "night_black", "mode": "attack", "card": card, "vuln_id": vuln.vid}
        return pid, {"type": "night_black", "mode": "pass"}

    if game.phase == Phase.NIGHT_WHITE:
        defender = game.pending_defense_player
        if defender is None or defender == human_pid:
            return None
        pl = game.players[defender]
        pa = game.pending_attack
        if not pa:
            return None
        vuln = next(v for v in game.vulnerabilities if v.vid == pa.target_vuln_id)
        need = VULN_TO_DEFENSE.get(vuln.kind)
        if need and need in pl.hand:
            return defender, {"type": "night_white", "card": need}
        return defender, {"type": "night_white", "pass": True}

    if game.phase == Phase.NIGHT_GRAY:
        gray = next((p for p in game.players if p.role == Role.GRAY_HAT and not p.eliminated), None)
        if gray is None:
            return None
        if gray.pid == human_pid:
            return None
        g = gray.pid
        pl = game.players[g]
        if rng.random() < 0.6:
            return g, {"type": "night_gray", "mode": "pass"}
        for v in game.vulnerabilities:
            need_a = VULN_TO_ATTACK.get(v.kind)
            need_d = VULN_TO_DEFENSE.get(v.kind)
            for c in pl.hand:
                if need_d and c == need_d:
                    return g, {"type": "night_gray", "mode": "resolve", "vuln_id": v.vid, "card": c}
                if need_a and (c == need_a or c == OFF_ZERO_DAYS):
                    return g, {"type": "night_gray", "mode": "exploit", "vuln_id": v.vid, "card": c}
        return g, {"type": "night_gray", "mode": "pass"}

    return None


def run_bots(game: WerewolfGame, human_pid: int, max_steps: int = 200) -> int:
    """Execute bot actions until human input is needed. Returns step count."""
    steps = 0
    while steps < max_steps:
        act = choose_bot_action(game, human_pid)
        if act is None:
            break
        pid, payload = act
        ok, _ = game.apply_action(pid, payload)
        if not ok:
            break
        steps += 1
    return steps
