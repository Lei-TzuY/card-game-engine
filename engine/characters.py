"""Character definitions: starting stats, decks, and relics."""

import json
import os
from copy import deepcopy


DEFAULT_CHARACTER_ID = "ironclad"
CHARACTER_REQUIRED_FIELDS = {
    "name": str,
    "description": str,
    "max_hp": int,
    "max_energy": int,
    "starter_relics": list,
    "starter_deck": list,
    "card_pool": list,
}

DEFAULT_CHARACTERS = {
    "ironclad": {
        "name": "Ironclad",
        "description": "A warrior who grows stronger through combat and rage.",
        "max_hp": 80,
        "max_energy": 3,
        "color": "\033[91m",
        "starter_relics": ["burning_blood"],
        "starter_deck": ["strike", "strike", "strike", "strike", "strike",
                         "defend", "defend", "defend", "defend", "bash"],
        "card_pool": ["strike", "defend", "cleave", "bash", "pommel_strike", "intimidate", "inflame", "uppercut",
                      "iron_wave", "clothesline", "shrug_it_off", "twin_strike", "battle_trance", "flex", "apparition",
                      "metallicize", "spiked_body", "flame_barrier",
                      "barricade", "entrench", "power_through", "shockwave",
                      "whirlwind", "skewer"],
    },
    "silent": {
        "name": "Silent",
        "description": "An agile rogue who strikes with speed and applies poison.",
        "max_hp": 70,
        "max_energy": 3,
        "color": "\033[92m",
        "starter_relics": [],
        "starter_deck": ["strike", "strike", "strike", "strike", "strike",
                         "defend", "defend", "defend", "defend", "defend",
                         "neutralize"],
        "card_pool": ["strike", "defend", "neutralize", "deadly_poison", "poisoned_stab", "pommel_strike", "intimidate",
                      "dagger_throw", "footwork", "crippling_cloud", "dodge_and_roll", "bouncing_flask", "apparition",
                      "self_repair", "terror", "skewer"],
    },
    "defect": {
        "name": "Defect",
        "description": "A rogue automaton that channels orb energy into powerful attacks.",
        "max_hp": 75,
        "max_energy": 3,
        "color": "\033[94m",
        "starter_relics": [],
        "starter_deck": ["strike", "strike", "strike", "strike",
                         "defend", "defend", "defend", "defend",
                         "zap", "dualcast"],
        "card_pool": ["strike", "defend", "zap", "dualcast", "coolheaded", "ball_lightning", "cleave",
                      "cold_snap", "sweeping_beam", "glacier", "compile_driver", "apparition", "self_repair", "shockwave"],
    },
    "watcher": {
        "name": "Watcher",
        "description": "A blind ascetic who has come to Evaluate the Spire.",
        "max_hp": 72,
        "max_energy": 3,
        "color": "\033[95m",
        "starter_relics": ["pure_water"],
        "starter_deck": ["strike", "strike", "strike", "strike",
                         "defend", "defend", "defend", "defend",
                         "eruption", "vigilance"],
        "card_pool": ["strike", "defend", "eruption", "vigilance", "consecrate", "empty_fist", "crescendo", "wreath_of_flame",
                      "sash_whip", "protect", "fear_no_evil", "tranquility", "apparition",
                      "spiked_body", "self_repair", "barricade"],
    },
    "sentinel": {
        "name": "Sentinel",
        "description": "A stalwart guardian who turns an unbreakable defense into a weapon.",
        "max_hp": 84,
        "max_energy": 3,
        "color": "\033[96m",
        "starter_relics": ["bronze_scales"],
        "starter_deck": ["strike", "strike", "strike", "strike",
                         "defend", "defend", "defend", "defend",
                         "body_slam", "iron_wave"],
        "card_pool": ["strike", "defend", "body_slam", "iron_wave", "shrug_it_off",
                      "power_through", "entrench", "barricade", "metallicize",
                      "spiked_body", "flame_barrier", "cleave", "bash", "whirlwind"],
    },
}


def _validate_character(character_id: str, data: dict):
    if not isinstance(data, dict):
        raise ValueError(f"Character {character_id} must be an object")
    for field, expected_type in CHARACTER_REQUIRED_FIELDS.items():
        if not isinstance(data.get(field), expected_type):
            raise ValueError(f"Character {character_id} has invalid {field}")
    if not data["starter_deck"]:
        raise ValueError(f"Character {character_id} starter_deck cannot be empty")
    if not data["card_pool"]:
        raise ValueError(f"Character {character_id} card_pool cannot be empty")


def _validate_characters(data: dict):
    if not isinstance(data, dict) or DEFAULT_CHARACTER_ID not in data:
        raise ValueError("Character data must include ironclad")
    for character_id, character in data.items():
        _validate_character(character_id, character)


def load_character_db(filepath="data/characters.json"):
    if not os.path.exists(filepath):
        return deepcopy(DEFAULT_CHARACTERS)
    with open(filepath, "r", encoding="utf-8") as character_file:
        data = json.load(character_file)
    _validate_characters(data)
    return data


CHARACTERS = load_character_db()


def get_character(char_id: str) -> dict:
    return CHARACTERS.get(char_id, CHARACTERS[DEFAULT_CHARACTER_ID])


def list_characters() -> list:
    return [(k, v) for k, v in CHARACTERS.items()]


def characters_to_dict() -> list:
    return [
        {
            "id": character_id,
            "name": character["name"],
            "description": character["description"],
            "max_hp": character["max_hp"],
            "max_energy": character["max_energy"],
        }
        for character_id, character in CHARACTERS.items()
    ]
