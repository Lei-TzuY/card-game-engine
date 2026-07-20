"""Persistent meta-progression: the highest Ascension level unlocked per character.

Stored separately from run saves so it survives across runs and run resets.
Ascension 0 is always available; winning a run at level N unlocks level N+1.
"""

import json
import os

from engine.ascension import MAX_ASCENSION, clamp_ascension

META_FILE = "data/meta.json"
META_VERSION = 1
HISTORY_CAP = 20
HISTORY_FIELDS = ("character", "ascension", "floor", "won", "gold", "score", "timestamp")


def _empty_meta() -> dict:
    return {"meta_version": META_VERSION, "ascension_unlocked": {}, "history": []}


def _clean_history(history) -> list:
    if not isinstance(history, list):
        return []
    cleaned = []
    for entry in history:
        if not isinstance(entry, dict):
            continue
        if not isinstance(entry.get("score"), int) or isinstance(entry.get("score"), bool):
            continue
        cleaned.append({field: entry.get(field) for field in HISTORY_FIELDS})
        if len(cleaned) >= HISTORY_CAP:
            break
    return cleaned


def load_meta(filepath: str = META_FILE) -> dict:
    if not os.path.exists(filepath):
        return _empty_meta()
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return _empty_meta()
    if not isinstance(data, dict):
        return _empty_meta()
    unlocked = data.get("ascension_unlocked")
    if not isinstance(unlocked, dict):
        unlocked = {}
    cleaned = {
        str(character_id): clamp_ascension(level)
        for character_id, level in unlocked.items()
        if isinstance(level, int) and not isinstance(level, bool)
    }
    return {
        "meta_version": META_VERSION,
        "ascension_unlocked": cleaned,
        "history": _clean_history(data.get("history")),
    }


def save_meta(meta: dict, filepath: str = META_FILE):
    os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
    temp_path = f"{filepath}.tmp"
    try:
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=4, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, filepath)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def max_unlocked(meta: dict, character_id: str) -> int:
    return clamp_ascension(meta.get("ascension_unlocked", {}).get(character_id, 0))


def is_ascension_allowed(meta: dict, character_id: str, ascension: int) -> bool:
    return 0 <= ascension <= max_unlocked(meta, character_id)


def record_victory(meta: dict, character_id: str, ascension: int) -> bool:
    """Unlock the next level after a win. Returns True if a new level was unlocked."""
    ascension = clamp_ascension(ascension)
    next_level = clamp_ascension(ascension + 1)
    current = max_unlocked(meta, character_id)
    if next_level <= current:
        return False
    meta.setdefault("ascension_unlocked", {})[character_id] = next_level
    return True


def record_run(meta: dict, summary: dict):
    """Prepend a finished-run summary to history, keeping only the most recent runs."""
    history = meta.setdefault("history", [])
    history.insert(0, {field: summary.get(field) for field in HISTORY_FIELDS})
    del history[HISTORY_CAP:]


def get_history(meta: dict) -> list:
    return meta.get("history", [])
