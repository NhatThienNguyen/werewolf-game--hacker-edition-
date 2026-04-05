"""JSON API for browser clients."""

from __future__ import annotations

import os
from typing import Any

from flask import Blueprint, jsonify, request, session

from game.bots import run_bots
from game.engine import WerewolfGame, new_game
from game.models import GameConfig

bp = Blueprint("api", __name__, url_prefix="/api")

GAMES: dict[str, WerewolfGame] = {}

HUMAN_PID = 0


def _session_game() -> WerewolfGame | None:
    gid = session.get("game_id")
    if not gid:
        return None
    return GAMES.get(gid)


def _json_error(msg: str, code: int = 400):
    return jsonify({"ok": False, "error": msg}), code


def _view(g: WerewolfGame) -> dict[str, Any]:
    run_bots(g, HUMAN_PID)
    data = g.to_view(HUMAN_PID)
    data["ok"] = True
    return data


@bp.post("/game/new")
def create_game():
    payload = request.get_json(silent=True) or {}
    try:
        n = int(payload.get("player_count", 5))
    except (TypeError, ValueError):
        return _json_error("player_count must be an integer")
    name = str(payload.get("name", "You")).strip() or "You"
    if n < 3 or n > 12:
        return _json_error("player_count must be between 3 and 12")

    g = new_game(GameConfig(player_count=n, human_name=name))
    GAMES[g.id] = g
    session["game_id"] = g.id
    return jsonify(_view(g))


@bp.get("/game/state")
def game_state():
    g = _session_game()
    if not g:
        return _json_error("No active game. Start a new one.", 404)
    return jsonify(_view(g))


@bp.post("/game/action")
def game_action():
    g = _session_game()
    if not g:
        return _json_error("No active game.", 404)
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return _json_error("JSON body required")
    ok, msg = g.apply_action(HUMAN_PID, payload)
    data = _view(g)
    if not ok:
        data["ok"] = False
        data["error"] = msg
    return jsonify(data)


@bp.post("/game/bots")
def tick_bots():
    """Advance bot moves until the human must act (mostly redundant with state)."""
    g = _session_game()
    if not g:
        return _json_error("No active game.", 404)
    return jsonify(_view(g))


def register_api(app):
    app.secret_key = os.environ.get("FLASK_SECRET_KEY", "werewolf-hacker-local-dev")
    app.register_blueprint(bp)
