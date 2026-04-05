"""Game engine: setup, phases, win conditions, and action dispatch."""

from __future__ import annotations

import copy
import random
import uuid
from typing import Any

from .constants import (
    DEFENSIVE_CARDS,
    MAX_HAND,
    NEUTRAL_ALL_IN,
    NEUTRAL_CARDS,
    NEUTRAL_DIGITAL_FORENSICS,
    NEUTRAL_IM_LEARNING,
    NEUTRAL_IM_OUT,
    NEUTRAL_INSPECT,
    NEUTRAL_SHOW_ME,
    NEUTRAL_TELL_ME_MORE,
    OFFENSIVE_CARDS,
    OFF_ZERO_DAYS,
    Role,
    VULN_TO_ATTACK,
    VULN_TO_DEFENSE,
    VULNERABILITY_TYPES,
)
from .models import GameConfig, PendingAttack, Phase, Player, Vulnerability


def _shuffle(rng: random.Random, deck: list[str]) -> None:
    rng.shuffle(deck)


def build_main_deck(rng: random.Random) -> list[str]:
    cards: list[str] = []
    for _ in range(4):
        cards.extend(NEUTRAL_CARDS)
    for _ in range(3):
        cards.extend(OFFENSIVE_CARDS)
        cards.extend(DEFENSIVE_CARDS)
    _shuffle(rng, cards)
    return cards


def roll_roles(player_count: int, rng: random.Random) -> list[Role]:
    """At least one White hat, Black hat, and Gray hat; remaining seats random among the three."""
    if player_count < 3:
        raise ValueError("Need at least 3 players.")

    roles: list[Role] = [Role.WHITE_HAT, Role.BLACK_HAT, Role.GRAY_HAT]
    for _ in range(player_count - 3):
        roles.append(rng.choice((Role.WHITE_HAT, Role.BLACK_HAT, Role.GRAY_HAT)))
    rng.shuffle(roles)
    return roles


def vuln_scale(player_count: int) -> int:
    if player_count < 5:
        return 3
    return player_count - 1


class WerewolfGame:
    def __init__(self, config: GameConfig, rng: random.Random | None = None):
        self.id = str(uuid.uuid4())
        self.rng = rng or random.Random()
        self.config = config
        self.players: list[Player] = []
        self.vulnerabilities: list[Vulnerability] = []
        self.deck: list[str] = []
        self.discard: list[str] = []
        self.phase: Phase = Phase.DAY_DRAW
        self.round_num = 1
        self.log: list[str] = []

        self.inspect_candidates: list[int] = []
        self.neutral_index: int = 0
        self.neutral_order: list[int] = []

        self.pending_attack: PendingAttack | None = None
        self.pending_defense_player: int | None = None
        self.last_wrong_attacker: int | None = None
        self.digital_forensics_available: bool = False

        self.vote_active: bool = False
        self.vote_target: int | None = None
        self.votes_cast: dict[int, int | None] = {}

        self.winner: str | None = None
        self.needs_discard: list[tuple[int, int]] = []  # (pid, over_by)
        self.night_black_actor: int | None = None

        self._setup()

    def _setup(self) -> None:
        n = self.config.player_count
        vuln_n = vuln_scale(n)
        roles = roll_roles(n, self.rng)

        names = [self.config.human_name] + [f"Bot {i}" for i in range(1, n)]
        self.players = [
            Player(pid=i, name=names[i], role=roles[i], is_human=(i == 0))
            for i in range(n)
        ]

        pool = list(VULNERABILITY_TYPES)
        kinds = [self.rng.choice(pool) for _ in range(vuln_n)]
        self.vulnerabilities = [Vulnerability(vid=i, kind=k) for i, k in enumerate(kinds)]

        self.deck = build_main_deck(self.rng)

        for p in self.players:
            self._draw_cards(p, 3)

        self._log(f"Game {self.id[:8]} — {n} players. Roles assigned secretly.")
        self._enter_day_draw()

    def _log(self, msg: str) -> None:
        self.log.append(msg)

    def living_players(self) -> list[Player]:
        return [p for p in self.players if not p.eliminated]

    def _draw_cards(self, player: Player, count: int) -> None:
        for _ in range(count):
            if not self.deck:
                self._reshuffle_discard_into_deck()
            if not self.deck:
                break
            player.hand.append(self.deck.pop())

    def _reshuffle_discard_into_deck(self) -> None:
        if not self.discard:
            return
        self.rng.shuffle(self.discard)
        self.deck.extend(self.discard)
        self.discard.clear()

    def _trim_hand(self, player: Player) -> None:
        over = len(player.hand) - MAX_HAND
        if over > 0:
            self.needs_discard.append((player.pid, over))

    def _enter_day_draw(self) -> None:
        self.phase = Phase.DAY_DRAW
        self.needs_discard.clear()
        for p in self.living_players():
            if p.skip_next_turn:
                p.skip_next_turn = False
                self._log(f"{p.name} skips draw (I'm out).")
                continue
            bonus = 1 if p.im_out_next_card_bonus else 0
            p.im_out_next_card_bonus = False
            self._draw_cards(p, 1 + bonus)
            self._trim_hand(p)

        if self.needs_discard:
            return

        self._begin_inspect_phase()

    def _begin_inspect_phase(self) -> None:
        self.phase = Phase.DAY_INSPECT
        self.inspect_candidates = [
            p.pid for p in self.living_players() if NEUTRAL_INSPECT in p.hand
        ]
        if len(self.inspect_candidates) > 1:
            pick = self.rng.choice(self.inspect_candidates)
            self._log("Multiple Inspect cards — one inspector is chosen at random.")
            self._perform_inspect(pick)
        elif len(self.inspect_candidates) == 1:
            self._perform_inspect(self.inspect_candidates[0])
        else:
            self._log("No Inspect plays today.")
            self._begin_neutral_phase()

    def _perform_inspect(self, pid: int) -> None:
        player = self.players[pid]
        if NEUTRAL_INSPECT not in player.hand:
            self._log(f"{player.name} cannot Inspect (no card).")
            self._begin_neutral_phase()
            return
        player.hand.remove(NEUTRAL_INSPECT)
        self.discard.append(NEUTRAL_INSPECT)
        hidden = [v for v in self.vulnerabilities if v.status == "hidden"]
        if not hidden:
            self._log(f"{player.name} inspects but no hidden vulnerabilities remain.")
        else:
            v = hidden[0]
            v.status = "known"
            v.discovered_by = pid
            v.public = False
            self._log(
                f"{player.name} inspects a vulnerability: {v.kind} "
                f"(known to their role)."
            )
        self.inspect_candidates.clear()
        self._begin_neutral_phase()

    def _begin_neutral_phase(self) -> None:
        self.phase = Phase.DAY_NEUTRAL
        self.neutral_order = [p.pid for p in self.living_players()]
        self.neutral_index = 0
        self._log("Neutral phase: each living player may play one neutral card or pass.")

    def _begin_discussion(self) -> None:
        self.phase = Phase.DAY_DISCUSSION
        self._log("Discussion — end the day when ready (or call a vote).")

    def _start_night(self) -> None:
        self.phase = Phase.NIGHT_BLACK
        self.pending_attack = None
        self.pending_defense_player = None
        self.digital_forensics_available = False
        blacks = [
            p.pid
            for p in self.living_players()
            if p.role == Role.BLACK_HAT
        ]
        self.night_black_actor = blacks[0] if blacks else None
        self._log("Night falls.")
        if self.night_black_actor is not None:
            self._log(f"{self.players[self.night_black_actor].name} acts for Black hats.")
        else:
            self._log("No Black hats in play — skipping Black night.")
            self._enter_gray_or_finish()

    def _vulnerability_counts(self) -> tuple[int, int, int]:
        total = len(self.vulnerabilities)
        resolved = sum(1 for v in self.vulnerabilities if v.status == "resolved")
        exploited = sum(1 for v in self.vulnerabilities if v.status == "exploited")
        return total, resolved, exploited

    def _majority_threshold(self) -> int:
        living = len(self.living_players())
        return living // 2 + 1

    def _check_win(self) -> None:
        total, resolved, exploited = self._vulnerability_counts()
        if total == 0:
            return
        half = total / 2

        white_alive = any(p.role == Role.WHITE_HAT and not p.eliminated for p in self.players)
        black_alive = any(p.role == Role.BLACK_HAT and not p.eliminated for p in self.players)

        if resolved > half:
            self.winner = "White hats (majority of vulnerabilities resolved)"
            self.phase = Phase.GAME_OVER
            return
        if exploited > half:
            self.winner = "Black hats (majority of vulnerabilities exploited)"
            self.phase = Phase.GAME_OVER
            return
        if not black_alive:
            self.winner = "White hats (Black hats eliminated)"
            self.phase = Phase.GAME_OVER
            return
        if not white_alive:
            self.winner = "Black hats (White hats eliminated)"
            self.phase = Phase.GAME_OVER

    def apply_action(self, pid: int, action: dict[str, Any]) -> tuple[bool, str]:
        kind = action.get("type")
        if self.phase == Phase.GAME_OVER:
            return False, "Game is over."

        if kind == "discard_down":
            slots = {p for p, _ in self.needs_discard}
            if pid not in slots:
                return False, "No discard required."
            indices = sorted(action.get("indices", []), reverse=True)
            need = next(n for p, n in self.needs_discard if p == pid)
            if len(indices) != need:
                return False, f"Must discard exactly {need} card(s)."
            pl = self.players[pid]
            for i in indices:
                if i < 0 or i >= len(pl.hand):
                    return False, "Bad card index."
            for i in indices:
                c = pl.hand.pop(i)
                self.discard.append(c)
            self.needs_discard = [(p, n) for p, n in self.needs_discard if p != pid]
            if not self.needs_discard:
                self._begin_inspect_phase()
            return True, "Discarded."

        if kind == "neutral_play":
            return self._neutral_play(pid, action)

        if kind == "neutral_pass":
            return self._neutral_pass(pid)

        if kind == "end_discussion":
            if self.phase != Phase.DAY_DISCUSSION:
                return False, "Not in discussion."
            self._start_night()
            return True, "Night begins."

        if kind == "start_vote":
            if self.phase != Phase.DAY_DISCUSSION:
                return False, "Votes can start from discussion."
            tgt = int(action["target_pid"])
            if self.players[tgt].eliminated:
                return False, "Target eliminated."
            self.phase = Phase.DAY_VOTE
            self.vote_active = True
            self.vote_target = tgt
            self.votes_cast = {p.pid: None for p in self.living_players()}
            self._log(f"Vote to eliminate {self.players[tgt].name} — cast votes.")
            return True, "Vote started."

        if kind == "vote":
            return self._vote(pid, int(action["target_pid"]))

        if kind == "night_black":
            return self._night_black_action(pid, action)

        if kind == "night_white":
            return self._night_white_action(pid, action)

        if kind == "night_gray":
            return self._night_gray_action(pid, action)

        if kind == "forensics":
            if self.phase not in (Phase.DAY_DISCUSSION, Phase.DAY_VOTE):
                return False, "Digital Forensics can be played during the day."
            return self._forensics(pid)

        return False, "Unknown action."

    def _neutral_pass(self, pid: int) -> tuple[bool, str]:
        if self.phase != Phase.DAY_NEUTRAL:
            return False, "Not neutral phase."
        if self.neutral_index >= len(self.neutral_order):
            return False, "Neutral phase over."
        if self.neutral_order[self.neutral_index] != pid:
            return False, "Not your neutral turn."
        self.neutral_index += 1
        if self.neutral_index >= len(self.neutral_order):
            self._begin_discussion()
        return True, "Pass."

    def _neutral_play(self, pid: int, action: dict[str, Any]) -> tuple[bool, str]:
        if self.phase != Phase.DAY_NEUTRAL:
            return False, "Not neutral phase."
        if self.neutral_index >= len(self.neutral_order):
            return False, "Neutral phase over."
        if self.neutral_order[self.neutral_index] != pid:
            return False, "Not your neutral turn."
        card = str(action["card"])
        if card not in NEUTRAL_CARDS:
            return False, "Not a neutral card."
        pl = self.players[pid]
        if card not in pl.hand:
            return False, "Card not in hand."

        pl.hand.remove(card)
        self.discard.append(card)

        if card == NEUTRAL_IM_LEARNING:
            self._draw_cards(pl, 2)
            self._trim_hand(pl)
            self._log(f"{pl.name} plays I'm learning and draws 2.")
        elif card == NEUTRAL_TELL_ME_MORE:
            known = [v for v in self.vulnerabilities if v.status != "hidden"]
            if known:
                v = known[0]
                self._log(f"Tell me more: defenders must share detail on {v.kind}.")
            else:
                self._log("Tell me more fizzles — no discovered vulnerability.")
        elif card == NEUTRAL_IM_OUT:
            pl.skip_next_turn = True
            pl.im_out_next_card_bonus = True
            self._log(f"{pl.name} plays I'm out — skips next round, +1 card next draw.")
        elif card == NEUTRAL_SHOW_ME:
            tgt = int(action.get("target_pid", -1))
            if tgt < 0 or tgt >= len(self.players):
                return False, "Invalid target for Show me what you got."
            victim = self.players[tgt]
            shown = ", ".join(victim.hand[:2]) if victim.hand else "(empty)"
            self._log(f"{pl.name} forces {victim.name} to reveal (up to 2 cards): {shown}")
        elif card == NEUTRAL_ALL_IN:
            pl.all_in_active = True
            pl.skip_next_turn = True
            self._log(f"{pl.name} plays All in — two actions this turn, skips next turn.")
        else:
            self._log(f"{pl.name} plays {card}.")

        self.neutral_index += 1
        if self.needs_discard:
            return True, "Neutral played; discard required."
        if self.neutral_index >= len(self.neutral_order):
            self._begin_discussion()
        return True, "Neutral played."

    def _vote(self, pid: int, target_pid: int) -> tuple[bool, str]:
        if not self.vote_active or self.phase != Phase.DAY_VOTE:
            return False, "No active vote."
        self.votes_cast[pid] = target_pid
        if any(v is None for v in self.votes_cast.values()):
            return True, "Vote recorded."

        counts: dict[int, int] = {}
        for v in self.votes_cast.values():
            if v is None:
                continue
            counts[v] = counts.get(v, 0) + 1
        top = max(counts, key=lambda k: counts[k])
        if counts[top] < self._majority_threshold():
            self._log("Vote failed — no majority.")
            self.vote_active = False
            self.phase = Phase.DAY_DISCUSSION
            return True, "Vote failed."

        victim = self.players[top]
        victim.elimination_votes_survived += 1
        cost = 2 * victim.elimination_votes_survived
        if len(victim.hand) < cost or len(victim.hand) == cost:
            victim.eliminated = True
            self._log(f"{victim.name} eliminated by vote (cannot pay {cost} cards).")
        else:
            for _ in range(cost):
                victim.hand.pop(self.rng.randrange(len(victim.hand)))
            self._log(f"{victim.name} survives vote but pays {cost} cards.")

        self.vote_active = False
        self._check_win()
        if self.phase != Phase.GAME_OVER:
            self.phase = Phase.DAY_DISCUSSION
        return True, "Vote resolved."

    def _night_black_action(self, pid: int, action: dict[str, Any]) -> tuple[bool, str]:
        if self.phase != Phase.NIGHT_BLACK:
            return False, "Not Black night phase."
        if self.night_black_actor is not None and pid != self.night_black_actor:
            return False, "Not the acting Black hat."
        pl = self.players[pid]
        if pl.role != Role.BLACK_HAT:
            return False, "Only Black hats act in this phase."
        mode = action.get("mode")
        if mode == "inspect":
            if NEUTRAL_INSPECT not in pl.hand:
                return False, "No Inspect card."
            pl.hand.remove(NEUTRAL_INSPECT)
            self.discard.append(NEUTRAL_INSPECT)
            hidden = [v for v in self.vulnerabilities if v.status == "hidden"]
            if hidden:
                v = hidden[0]
                v.status = "known"
                v.discovered_by = pid
                self._log(f"{pl.name} (night) inspects: {v.kind}.")
            self._advance_night_from_black()
            return True, "Night inspect done."

        if mode == "attack":
            card = str(action["card"])
            vid = int(action["vuln_id"])
            if card not in pl.hand:
                return False, "Card not in hand."
            vuln = next((v for v in self.vulnerabilities if v.vid == vid), None)
            if not vuln:
                return False, "Bad vulnerability id."
            pl.hand.remove(card)
            self.discard.append(card)
            expected = VULN_TO_ATTACK.get(vuln.kind)
            wrong = card != OFF_ZERO_DAYS and (expected is None or card != expected)
            if wrong:
                self.last_wrong_attacker = pid
                self.digital_forensics_available = True
                self._log(
                    f"{pl.name} attacks the wrong vulnerability — new vulnerability added; "
                    "a White hat may use Digital Forensics."
                )
                extra_kind = self.rng.choice(list(VULNERABILITY_TYPES))
                self.vulnerabilities.append(
                    Vulnerability(vid=len(self.vulnerabilities), kind=extra_kind)
                )
                self._advance_night_from_black()
                return True, "Wrong attack."

            self.pending_attack = PendingAttack(pid, vid, card, False)
            self.pending_defense_player = next(
                (
                    p.pid
                    for p in self.living_players()
                    if p.role == Role.WHITE_HAT
                ),
                None,
            )
            if self.pending_defense_player is None:
                vuln.status = "exploited"
                self._log(
                    f"{pl.name} attacks {vuln.kind} — no White hat alive; vulnerability exploited."
                )
                self.pending_attack = None
                self._enter_gray_or_finish()
                return True, "Attack succeeds (no defender)."

            self.phase = Phase.NIGHT_WHITE
            self._log(f"{pl.name} launches a correct attack — White hat may respond.")
            return True, "Attack pending defense."

        if mode == "pass":
            self._advance_night_from_black()
            return True, "Pass."

        return False, "Unknown night action."

    def _advance_night_from_black(self) -> None:
        if self.pending_attack is not None:
            self.phase = Phase.NIGHT_WHITE
            return
        self._enter_gray_or_finish()

    def _night_white_action(self, pid: int, action: dict[str, Any]) -> tuple[bool, str]:
        if self.phase != Phase.NIGHT_WHITE:
            return False, "White hat not needed."
        if self.pending_attack is None:
            return False, "No pending attack."
        if self.pending_defense_player is not None and pid != self.pending_defense_player:
            return False, "Not the defending White hat."
        pl = self.players[pid]
        if pl.role != Role.WHITE_HAT:
            return False, "Only White hat."
        pa = self.pending_attack
        vuln = next(v for v in self.vulnerabilities if v.vid == pa.target_vuln_id)
        if action.get("pass"):
            vuln.status = "exploited"
            self._log(f"{pl.name} fails to stop the attack — {vuln.kind} exploited.")
            self.pending_attack = None
            self._enter_gray_or_finish()
            return True, "Attack succeeds."

        card = str(action["card"])
        if card not in pl.hand:
            return False, "Card not in hand."
        need = VULN_TO_DEFENSE.get(vuln.kind)
        if card != need:
            extra_kind = self.rng.choice(list(VULNERABILITY_TYPES))
            self.vulnerabilities.append(
                Vulnerability(vid=len(self.vulnerabilities), kind=extra_kind)
            )
            self._log(
                f"{pl.name} used the wrong defense — a new vulnerability appears: {extra_kind}."
            )
            self.pending_attack = None
            self._enter_gray_or_finish()
            return True, "Wrong defense — new vulnerability."

        pl.hand.remove(card)
        self.discard.append(card)
        vuln.status = "resolved"
        self._log(f"{pl.name} stops the attack — {vuln.kind} resolved.")
        self.pending_attack = None
        self._enter_gray_or_finish()
        return True, "Defense successful."

    def _night_gray_action(self, pid: int, action: dict[str, Any]) -> tuple[bool, str]:
        if self.phase != Phase.NIGHT_GRAY:
            return False, "Not Gray night."
        pl = self.players[pid]
        if pl.role != Role.GRAY_HAT:
            return False, "Only Gray hat."
        mode = action.get("mode")
        if mode == "pass":
            self._finish_night()
            return True, "Gray passes."

        if mode == "resolve":
            vid = int(action["vuln_id"])
            card = str(action["card"])
            vuln = next((v for v in self.vulnerabilities if v.vid == vid), None)
            if not vuln or card not in pl.hand:
                return False, "Bad resolve."
            need = VULN_TO_DEFENSE.get(vuln.kind)
            if card != need:
                return False, "Mismatch."
            pl.hand.remove(card)
            self.discard.append(card)
            vuln.status = "resolved"
            self._log(f"{pl.name} (Gray) resolves {vuln.kind}.")
            self._finish_night()
            return True, "Resolved."

        if mode == "exploit":
            vid = int(action["vuln_id"])
            card = str(action["card"])
            vuln = next((v for v in self.vulnerabilities if v.vid == vid), None)
            if not vuln or card not in pl.hand:
                return False, "Bad exploit."
            need = VULN_TO_ATTACK.get(vuln.kind)
            if card != OFF_ZERO_DAYS and card != need:
                return False, "Mismatch."
            pl.hand.remove(card)
            self.discard.append(card)
            vuln.status = "exploited"
            self._log(f"{pl.name} (Gray) exploits {vuln.kind}.")
            self._finish_night()
            return True, "Exploited."

        return False, "Unknown gray action."

    def _enter_gray_or_finish(self) -> None:
        if any(p.role == Role.GRAY_HAT and not p.eliminated for p in self.players):
            self.phase = Phase.NIGHT_GRAY
            return
        self._finish_night()

    def _forensics(self, pid: int) -> tuple[bool, str]:
        pl = self.players[pid]
        if pl.role != Role.WHITE_HAT:
            return False, "Only a White hat may play Digital Forensics."
        if not self.digital_forensics_available or NEUTRAL_DIGITAL_FORENSICS not in pl.hand:
            return False, "Forensics unavailable."
        if self.last_wrong_attacker is None:
            return False, "No culprit tracked."
        pl.hand.remove(NEUTRAL_DIGITAL_FORENSICS)
        self.discard.append(NEUTRAL_DIGITAL_FORENSICS)
        name = self.players[self.last_wrong_attacker].name
        self._log(f"{pl.name} uses Digital Forensics — attacker was {name}.")
        self.digital_forensics_available = False
        return True, "Forensics used."

    def _player_sees_vuln_kind(self, viewer: Player, v: Vulnerability) -> bool:
        if v.discovered_by is None:
            return False
        if v.discovered_by == viewer.pid:
            return True
        discoverer = self.players[v.discovered_by]
        return discoverer.role == viewer.role

    def _finish_night(self) -> None:
        self.night_black_actor = None
        self.pending_defense_player = None
        self._check_win()
        if self.phase == Phase.GAME_OVER:
            return
        self.round_num += 1
        self._log(f"— Round {self.round_num} —")
        self._enter_day_draw()

    def to_view(self, human_pid: int) -> dict[str, Any]:
        """Player-centric snapshot for API/UI."""
        hp = self.players[human_pid]
        vulns_out = []
        for v in self.vulnerabilities:
            vulns_out.append(
                {
                    "id": v.vid,
                    "kind": v.kind if self._player_sees_vuln_kind(hp, v) else "?",
                }
            )

        players_out = []
        for p in self.players:
            entry: dict[str, Any] = {
                "pid": p.pid,
                "name": p.name,
                "eliminated": p.eliminated,
                "is_human": p.is_human,
            }
            if p.pid == human_pid:
                entry["role"] = p.role.value
                entry["hand"] = list(p.hand)
            elif p.role == hp.role:
                entry["role"] = p.role.value
                entry["same_role"] = True
                entry["hand_count"] = len(p.hand)
            else:
                entry["role"] = "hidden"
                entry["hand_count"] = len(p.hand)
            players_out.append(entry)

        return {
            "game_id": self.id,
            "phase": self.phase.value,
            "round": self.round_num,
            "you": human_pid,
            "players": players_out,
            "vulnerabilities": vulns_out,
            "log": list(self.log[-40:]),
            "winner": self.winner,
            "needs_discard": [
                {"pid": p, "amount": n} for p, n in self.needs_discard
            ],
            "neutral_turn": self.neutral_order[self.neutral_index]
            if self.phase == Phase.DAY_NEUTRAL and self.neutral_index < len(self.neutral_order)
            else None,
            "pending_attack": copy.deepcopy(self.pending_attack.__dict__) if self.pending_attack else None,
            "digital_forensics_available": self.digital_forensics_available,
            "vote_active": self.vote_active,
            "vote_target": self.vote_target,
            "night_black_actor": self.night_black_actor,
            "pending_defense_player": self.pending_defense_player,
        }


def new_game(config: GameConfig, rng: random.Random | None = None) -> WerewolfGame:
    return WerewolfGame(config, rng)
