import logging
import os
import re
import time
import uuid
from dataclasses import dataclass, field
from functools import wraps
from threading import RLock

from flask import Flask, jsonify, request, session as browser_session
from werkzeug.exceptions import HTTPException

from engine.ascension import (
    MAX_ASCENSION,
    ascension_levels,
    clamp_ascension,
    starting_hp_fraction,
)
from engine.characters import CHARACTERS, characters_to_dict, get_character
from engine.database import CardDatabase
from engine.entities import Enemy, Player
from engine.game import Game
from engine.meta import (
    get_history,
    is_ascension_allowed,
    load_meta,
    record_run,
    record_victory,
    save_meta,
)
from engine.session import Session

DEV_SECRET_KEY = "card-game-engine-development-key"

app = Flask(__name__, static_folder='static')
app.secret_key = os.environ.get("CARD_GAME_SECRET_KEY", DEV_SECRET_KEY)

db = CardDatabase()
db.load_from_file("data/cards.json")

SAVE_DIR = "data/runs"
COMBAT_NODE_TYPES = {"Enemy", "Elite", "Boss"}
SLOT_IDS = ("slot_1", "slot_2", "slot_3")


def env_int(name: str, default: int):
    value = os.environ.get(name)
    return default if value is None else int(value)


def env_float(name: str, default: float):
    value = os.environ.get(name)
    return default if value is None else float(value)


def env_bool(name: str, default: bool = False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


RUN_TTL_SECONDS = env_int("CARD_GAME_RUN_TTL_SECONDS", 7 * 24 * 60 * 60)
RUN_CLEANUP_INTERVAL_SECONDS = env_int("CARD_GAME_RUN_CLEANUP_INTERVAL_SECONDS", 5 * 60)
RUN_LOCK_TIMEOUT_SECONDS = env_float("CARD_GAME_RUN_LOCK_TIMEOUT_SECONDS", 5.0)
RUN_LOCK_STALE_SECONDS = env_float("CARD_GAME_RUN_LOCK_STALE_SECONDS", 30.0)
SERVER_HOST = os.environ.get("CARD_GAME_HOST", "127.0.0.1")
SERVER_PORT = env_int("CARD_GAME_PORT", 5000)
SERVER_DEBUG = env_bool("CARD_GAME_DEBUG", False)
REQUIRE_SECRET_KEY = env_bool("CARD_GAME_REQUIRE_SECRET", False)
LOG_LEVEL = os.environ.get("CARD_GAME_LOG_LEVEL", "INFO").upper()
RUN_SAVE_PATTERN = re.compile(
    r"^(?P<run_id>(?:[0-9a-f]{32}|slot_[123]))\.json(?:\.bak)?"
    r"(?:\.tmp|\.invalid-\d{8}T\d{6}Z(?:-\d+)?)?$"
)


def configure_logging():
    level = getattr(logging, LOG_LEVEL, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    app.logger.setLevel(level)


def using_development_secret():
    return app.secret_key == DEV_SECRET_KEY


def validate_app_config(require_secret: bool = None):
    require_secret = REQUIRE_SECRET_KEY if require_secret is None else require_secret
    if require_secret and (not app.secret_key or using_development_secret() or len(app.secret_key) < 32):
        raise RuntimeError(
            "Set CARD_GAME_SECRET_KEY to a non-default value of at least 32 characters "
            "before running in production."
        )


configure_logging()
validate_app_config()


@dataclass
class RunState:
    session: Session
    game: Game = None
    lock: RLock = field(default_factory=RLock, repr=False)
    last_access: float = field(default_factory=time.time)
    storage_mtime: float = 0.0


runs: dict[str, RunState] = {}
runs_lock = RLock()
cleanup_lock = RLock()
meta_lock = RLock()
_last_cleanup_at = 0.0


def meta_payload():
    with meta_lock:
        meta = load_meta()
    return {
        "max_ascension": MAX_ASCENSION,
        "levels": ascension_levels(),
        "unlocked": meta.get("ascension_unlocked", {}),
        "history": get_history(meta),
    }


def finalize_if_run_over(session):
    """Once a run reaches GAME_OVER, unlock ascension (on win) and log it to history."""
    if session.phase != "GAME_OVER" or getattr(session, "_run_recorded", False):
        return
    session._run_recorded = True
    won = bool(getattr(session, "run_won", False)) and session.player and not session.player.is_dead()
    with meta_lock:
        meta = load_meta()
        if won:
            record_victory(meta, session.character_id, session.ascension)
        record_run(meta, session.run_summary())
        save_meta(meta)


def _new_run_id():
    run_id = uuid.uuid4().hex
    browser_session["run_id"] = run_id
    return run_id


def is_slot_id(run_id: str):
    return run_id in SLOT_IDS


def is_uuid_run_id(run_id: str):
    if not run_id:
        return False
    try:
        parsed_run_id = uuid.UUID(hex=run_id)
    except (AttributeError, TypeError, ValueError):
        return False
    return parsed_run_id.hex == run_id


def is_valid_run_id(run_id: str):
    return is_slot_id(run_id) or is_uuid_run_id(run_id)


def _get_run_id():
    run_id = browser_session.get("run_id")
    if not is_valid_run_id(run_id):
        return _new_run_id()
    return run_id


def save_filepath(run_id: str):
    return os.path.join(SAVE_DIR, f"{run_id}.json")


def lock_filepath(run_id: str):
    return os.path.join(SAVE_DIR, f"{run_id}.lock")


def _run_save_filepaths(run_id: str):
    if not os.path.isdir(SAVE_DIR):
        return []
    filepaths = []
    for entry in os.scandir(SAVE_DIR):
        match = RUN_SAVE_PATTERN.fullmatch(entry.name)
        if entry.is_file() and match and match.group("run_id") == run_id:
            filepaths.append(entry.path)
    return filepaths


def _run_storage_mtime(run_id: str):
    mtimes = [os.path.getmtime(path) for path in _run_save_filepaths(run_id)]
    return max(mtimes) if mtimes else 0.0


class RunFileLock:
    def __init__(self, run_id: str, timeout_seconds: float = None, stale_seconds: float = None):
        self.run_id = run_id
        self.timeout_seconds = RUN_LOCK_TIMEOUT_SECONDS if timeout_seconds is None else timeout_seconds
        self.stale_seconds = RUN_LOCK_STALE_SECONDS if stale_seconds is None else stale_seconds
        self.filepath = lock_filepath(run_id)
        self.acquired = False

    def __enter__(self):
        os.makedirs(os.path.dirname(os.path.abspath(self.filepath)), exist_ok=True)
        deadline = time.monotonic() + self.timeout_seconds
        while True:
            try:
                fd = os.open(self.filepath, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                if self._remove_if_stale() or time.monotonic() < deadline:
                    time.sleep(0.025)
                    continue
                raise TimeoutError("Run is busy. Please retry.")
            else:
                with os.fdopen(fd, "w", encoding="utf-8") as lock_file:
                    lock_file.write(f"{os.getpid()} {time.time()}\n")
                self.acquired = True
                return self

    def __exit__(self, exc_type, exc, traceback):
        if not self.acquired:
            return
        try:
            os.remove(self.filepath)
        except FileNotFoundError:
            pass

    def _remove_if_stale(self):
        try:
            lock_age = time.time() - os.path.getmtime(self.filepath)
        except FileNotFoundError:
            return True
        if lock_age < self.stale_seconds:
            return False
        try:
            os.remove(self.filepath)
        except FileNotFoundError:
            return True
        return True


def delete_save_files(run_id: str):
    for filepath in _run_save_filepaths(run_id):
        try:
            os.remove(filepath)
        except FileNotFoundError:
            pass


def cleanup_stale_runs(now: float = None, force: bool = False):
    global _last_cleanup_at
    now = time.time() if now is None else now
    with cleanup_lock:
        if not force and now - _last_cleanup_at < RUN_CLEANUP_INTERVAL_SECONDS:
            return []
        _last_cleanup_at = now

        removed_run_ids = set()
        with runs_lock:
            candidates = [
                (run_id, run)
                for run_id, run in runs.items()
                if now - run.last_access >= RUN_TTL_SECONDS
            ]

        for run_id, run in candidates:
            if not run.lock.acquire(blocking=False):
                continue
            try:
                with runs_lock:
                    if runs.get(run_id) is run and now - run.last_access >= RUN_TTL_SECONDS:
                        del runs[run_id]
                        removed_run_ids.add(run_id)
            finally:
                run.lock.release()

        with runs_lock:
            active_run_ids = set(runs)
        orphan_modified_at = {}
        if os.path.isdir(SAVE_DIR):
            for entry in os.scandir(SAVE_DIR):
                match = RUN_SAVE_PATTERN.fullmatch(entry.name)
                if not entry.is_file() or not match:
                    continue
                run_id = match.group("run_id")
                if is_slot_id(run_id) or run_id in active_run_ids:
                    continue
                orphan_modified_at[run_id] = max(
                    orphan_modified_at.get(run_id, 0),
                    entry.stat().st_mtime,
                )

        for run_id, modified_at in orphan_modified_at.items():
            if is_uuid_run_id(run_id) and (run_id in removed_run_ids or now - modified_at >= RUN_TTL_SECONDS):
                delete_save_files(run_id)
                removed_run_ids.add(run_id)

        return sorted(removed_run_ids)


def _load_run(run_id: str):
    loaded_session = Session.load_from_file(save_filepath(run_id))
    if not loaded_session:
        return RunState(Session(), storage_mtime=_run_storage_mtime(run_id))
    if loaded_session.phase != "COMBAT":
        return RunState(loaded_session, storage_mtime=_run_storage_mtime(run_id))
    if not loaded_session.combat_state:
        return RunState(Session(), storage_mtime=_run_storage_mtime(run_id))
    game = Game.from_save_dict(loaded_session.player, loaded_session.combat_state, db, loaded_session.relics)
    return RunState(loaded_session, game, storage_mtime=_run_storage_mtime(run_id))


def _get_or_create_run(run_id: str):
    with runs_lock:
        if run_id not in runs:
            runs[run_id] = _load_run(run_id)
        run = runs[run_id]
        run.last_access = time.time()
    return run


def refresh_run_from_storage(run_id: str, run: RunState):
    storage_mtime = _run_storage_mtime(run_id)
    if not storage_mtime or storage_mtime <= run.storage_mtime:
        return
    latest = _load_run(run_id)
    run.session = latest.session
    run.game = latest.game
    run.storage_mtime = latest.storage_mtime


def get_run_context():
    cleanup_stale_runs()
    run_id = _get_run_id()
    run = _get_or_create_run(run_id)
    return run_id, run


def get_run():
    return get_run_context()[1]


def save_run(run_id: str, run: RunState):
    run.session.save_to_file(save_filepath(run_id), run.game)
    run.storage_mtime = _run_storage_mtime(run_id)


def reset_run(run_id: str, run: RunState):
    delete_save_files(run_id)
    run.session = Session()
    run.game = None
    run.storage_mtime = 0.0


def with_run_lock(handler):
    @wraps(handler)
    def wrapped(*args, **kwargs):
        run_id, run = get_run_context()
        with run.lock:
            run.last_access = time.time()
            try:
                with RunFileLock(run_id):
                    refresh_run_from_storage(run_id, run)
                    return handler(run_id, run, *args, **kwargs)
            except TimeoutError as exc:
                return jsonify({"error": str(exc)}), 409
    return wrapped


def bind_test_run(client, session: Session, game: Game = None, run_id: str = None):
    """Attach a deterministic isolated run to a Flask test client."""
    run_id = run_id or uuid.uuid4().hex
    with client.session_transaction() as cookie:
        cookie["run_id"] = run_id
    run = RunState(session, game, storage_mtime=_run_storage_mtime(run_id))
    with runs_lock:
        runs[run_id] = run
    return run


@app.route('/')
def index():
    return app.send_static_file('index.html')


def is_api_request():
    return request.path.startswith("/api/")


@app.errorhandler(HTTPException)
def handle_http_error(exc):
    if is_api_request():
        return jsonify({"error": exc.description}), exc.code
    return exc


@app.errorhandler(Exception)
def handle_unexpected_error(exc):
    app.logger.exception("Unhandled request error")
    if is_api_request():
        return jsonify({"error": "Internal server error"}), 500
    raise exc


def state_response(run: RunState):
    res = {
        "session": run.session.to_dict(),
        "cards": db.to_dict(),
        "characters": characters_to_dict(),
        "meta": meta_payload(),
    }
    if run.session.phase == "COMBAT" and run.game:
        res["game"] = run.game.to_dict()
    return jsonify(res)


@app.route('/api/meta', methods=['GET'])
def get_meta():
    return jsonify(meta_payload())


@app.route('/api/state', methods=['GET'])
@with_run_lock
def get_state(run_id, run):
    return state_response(run)


@app.route('/api/health', methods=['GET'])
def health():
    with runs_lock:
        runs_in_memory = len(runs)
    return jsonify({
        "status": "ok",
        "save_dir": SAVE_DIR,
        "secret_configured": not using_development_secret(),
        "runs_in_memory": runs_in_memory,
        "slots": list(SLOT_IDS),
    })


@app.route('/api/slots', methods=['GET'])
def get_slots():
    slots_data = {}
    for slot_id in SLOT_IDS:
        filepath = save_filepath(slot_id)
        session = Session.load_from_file(filepath)
        if session and session.player:
            slots_data[slot_id] = {
                "character": session.player.name,
                "floor": session.floor,
                "hp": session.player.hp,
                "max_hp": session.player.max_hp
            }
        else:
            slots_data[slot_id] = None
    return jsonify(slots_data)

@app.route('/api/load_slot', methods=['POST'])
def load_slot():
    data = request.get_json(silent=True) or {}
    slot_id = data.get("slot_id")
    if not is_slot_id(slot_id):
        return jsonify({"error": "Invalid slot"}), 400
    
    browser_session["run_id"] = slot_id
    cleanup_stale_runs()
    run = _get_or_create_run(slot_id)
    with run.lock:
        try:
            with RunFileLock(slot_id):
                latest = _load_run(slot_id)
                run.session = latest.session
                run.game = latest.game
                run.storage_mtime = latest.storage_mtime
                run.last_access = time.time()
                return state_response(run)
        except TimeoutError as exc:
            return jsonify({"error": str(exc)}), 409

@app.route('/api/delete_slot', methods=['POST'])
def delete_slot():
    data = request.get_json(silent=True) or {}
    slot_id = data.get("slot_id")
    if not is_slot_id(slot_id):
        return jsonify({"error": "Invalid slot"}), 400
    
    run = _get_or_create_run(slot_id)
    with run.lock:
        try:
            with RunFileLock(slot_id):
                delete_save_files(slot_id)
                run.session = Session()
                run.game = None
                run.storage_mtime = 0.0
                run.last_access = time.time()
        except TimeoutError as exc:
            return jsonify({"error": str(exc)}), 409
    
    if browser_session.get("run_id") == slot_id:
        browser_session.pop("run_id", None)
        
    return jsonify({"status": "success"})


@app.route('/api/choose_node', methods=['POST'])
@with_run_lock
def choose_node(run_id, run):
    data = request.get_json(silent=True) or {}
    node = run.session.choose_node(data.get("node_id"))
    if not node:
        return jsonify({"error": "Invalid node"}), 400

    run.game = None
    if node.type in COMBAT_NODE_TYPES:
        enemies = [
            Enemy(e["name"], e["hp"], e.get("attack", 5), e.get("actions"), e.get("phases"), e.get("passives"))
            for e in node.enemies_data
        ]
        run.game = Game(run.session.player, enemies, db, run.session.relics)
        run.game.setup_deck(run.session.master_deck)
        run.game.start_combat()
    save_run(run_id, run)
    return state_response(run)


@app.route('/api/start_run', methods=['POST'])
@with_run_lock
def start_run(run_id, run):
    if run.session.phase != "CHARACTER_SELECT":
        return jsonify({"error": "Run already started"}), 400

    data = request.get_json(silent=True) or {}
    character_id = data.get("character_id")
    if character_id not in CHARACTERS:
        return jsonify({"error": "Invalid character"}), 400

    ascension = clamp_ascension(data.get("ascension", 0))
    with meta_lock:
        meta = load_meta()
    if not is_ascension_allowed(meta, character_id, ascension):
        return jsonify({"error": "Ascension level is locked"}), 400

    character = get_character(character_id)
    player = Player(character["name"], character["max_hp"], character["max_energy"])
    run.session = Session(player, character_id=character_id, ascension=ascension)
    player.hp = max(1, int(player.max_hp * starting_hp_fraction(ascension)))
    run.game = None
    save_run(run_id, run)
    return state_response(run)


@app.route('/api/play', methods=['POST'])
@with_run_lock
def play_card(run_id, run):
    if run.session.phase != "COMBAT" or not run.game:
        return jsonify({"error": "Not in combat"}), 400

    data = request.get_json(silent=True) or {}
    index = data.get("index")
    target_index = data.get("target_index", 0)
    if index is None or not 0 <= index < len(run.game.hand):
        return jsonify({"error": "Invalid card index"}), 400
    if not run.game.play_card(index, target_index):
        return jsonify({"error": "Not enough energy"}), 400

    if run.game.is_game_over():
        run.session.end_combat(not run.session.player.is_dead())
        finalize_if_run_over(run.session)
    save_run(run_id, run)
    return state_response(run)


@app.route('/api/end_turn', methods=['POST'])
@with_run_lock
def end_turn(run_id, run):
    if run.session.phase != "COMBAT" or not run.game:
        return jsonify({"error": "Not in combat"}), 400

    run.game.end_player_turn()
    if run.game.is_game_over():
        run.session.end_combat(not run.session.player.is_dead())
        finalize_if_run_over(run.session)
    save_run(run_id, run)
    return state_response(run)


@app.route('/api/choose_reward', methods=['POST'])
@with_run_lock
def choose_reward(run_id, run):
    if run.session.phase != "REWARD":
        return jsonify({"error": "Not in reward phase"}), 400

    data = request.get_json(silent=True) or {}
    if not run.session.choose_reward(data.get("card_id")):
        return jsonify({"error": "Invalid reward choice"}), 400
    save_run(run_id, run)
    return state_response(run)


@app.route('/api/reward/relic', methods=['POST'])
@with_run_lock
def claim_relic_reward(run_id, run):
    if not run.session.claim_relic_reward():
        return jsonify({"error": "No relic reward available"}), 400
    save_run(run_id, run)
    return state_response(run)


@app.route('/api/potion/use', methods=['POST'])
@with_run_lock
def use_potion(run_id, run):
    if run.session.phase != "COMBAT" or not run.game:
        return jsonify({"error": "Not in combat"}), 400

    data = request.get_json(silent=True) or {}
    if not run.session.use_potion(data.get("potion_index"), run.game, data.get("target_index", 0)):
        return jsonify({"error": "Potion unavailable or target invalid"}), 400

    if run.game.is_game_over():
        run.session.end_combat(not run.session.player.is_dead())
        finalize_if_run_over(run.session)
    save_run(run_id, run)
    return state_response(run)


@app.route('/api/rest', methods=['POST'])
@with_run_lock
def complete_rest(run_id, run):
    data = request.get_json(silent=True) or {}
    if not run.session.complete_rest(data.get("action"), data.get("card_index"), db.can_upgrade):
        return jsonify({"error": "Invalid rest action"}), 400
    save_run(run_id, run)
    return state_response(run)


@app.route('/api/event', methods=['POST'])
@with_run_lock
def complete_event(run_id, run):
    data = request.get_json(silent=True) or {}
    if not run.session.complete_event(data.get("choice_id")):
        return jsonify({"error": "Invalid event choice"}), 400
    save_run(run_id, run)
    return state_response(run)


@app.route('/api/shop/buy', methods=['POST'])
@with_run_lock
def buy_shop_card(run_id, run):
    data = request.get_json(silent=True) or {}
    if not run.session.buy_card(data.get("card_id")):
        return jsonify({"error": "Card unavailable or not enough gold"}), 400
    save_run(run_id, run)
    return state_response(run)


@app.route('/api/shop/potion', methods=['POST'])
@with_run_lock
def buy_shop_potion(run_id, run):
    data = request.get_json(silent=True) or {}
    if not run.session.buy_potion(data.get("potion_id")):
        return jsonify({"error": "Potion unavailable, inventory full, or not enough gold"}), 400
    save_run(run_id, run)
    return state_response(run)


@app.route('/api/shop/remove', methods=['POST'])
@with_run_lock
def remove_shop_card(run_id, run):
    data = request.get_json(silent=True) or {}
    if not run.session.remove_card(data.get("card_index")):
        return jsonify({"error": "Card removal unavailable"}), 400
    save_run(run_id, run)
    return state_response(run)


@app.route('/api/shop/leave', methods=['POST'])
@with_run_lock
def leave_shop(run_id, run):
    if not run.session.leave_shop():
        return jsonify({"error": "Not in shop"}), 400
    save_run(run_id, run)
    return state_response(run)


@app.route('/api/abandon_run', methods=['POST'])
@with_run_lock
def abandon_run(run_id, run):
    reset_run(run_id, run)
    return state_response(run)


@app.route('/api/restart', methods=['POST'])
@with_run_lock
def restart(run_id, run):
    reset_run(run_id, run)
    return state_response(run)


if __name__ == '__main__':
    app.run(debug=SERVER_DEBUG, host=SERVER_HOST, port=SERVER_PORT)
