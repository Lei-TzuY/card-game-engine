import json
import os
from copy import deepcopy


DEFAULT_POTIONS_DB = {
    "fire_potion": {
        "id": "fire_potion",
        "name": "Fire Potion",
        "description": "Deal 20 damage to the first selected enemy.",
        "icon": "F",
    },
    "block_potion": {
        "id": "block_potion",
        "name": "Block Potion",
        "description": "Gain 12 Block.",
        "icon": "B",
    },
    "strength_potion": {
        "id": "strength_potion",
        "name": "Strength Potion",
        "description": "Gain 2 Strength for this combat.",
        "icon": "S",
    },
    "dexterity_potion": {
        "id": "dexterity_potion",
        "name": "Dexterity Potion",
        "description": "Gain 2 Dexterity for this combat.",
        "icon": "D",
    },
    "energy_potion": {
        "id": "energy_potion",
        "name": "Energy Potion",
        "description": "Gain 2 Energy.",
        "icon": "E",
    },
    "swift_potion": {
        "id": "swift_potion",
        "name": "Swift Potion",
        "description": "Draw 3 cards.",
        "icon": "SW",
    },
    "weak_potion": {
        "id": "weak_potion",
        "name": "Weak Potion",
        "description": "Apply 3 Weak to the selected enemy.",
        "icon": "WK",
    },
    "fear_potion": {
        "id": "fear_potion",
        "name": "Fear Potion",
        "description": "Apply 3 Vulnerable to the selected enemy.",
        "icon": "FR",
    },
    "blood_potion": {
        "id": "blood_potion",
        "name": "Blood Potion",
        "description": "Heal 25% of your maximum HP.",
        "icon": "BL",
    },
    "regen_potion": {
        "id": "regen_potion",
        "name": "Regeneration Potion",
        "description": "Gain 5 Regen (heal a decreasing amount each turn).",
        "icon": "RG",
    },
    "explosive_potion": {
        "id": "explosive_potion",
        "name": "Explosive Potion",
        "description": "Deal 10 damage to ALL enemies.",
        "icon": "EX",
    },
    "ancient_potion": {
        "id": "ancient_potion",
        "name": "Ancient Potion",
        "description": "Gain 1 Artifact (negates your next debuff).",
        "icon": "AR",
    },
}

POTION_REQUIRED_FIELDS = {
    "id": str,
    "name": str,
    "description": str,
    "icon": str,
}
IMPLEMENTED_POTION_IDS = {
    "fire_potion",
    "block_potion",
    "strength_potion",
    "dexterity_potion",
    "energy_potion",
    "swift_potion",
    "weak_potion",
    "fear_potion",
    "blood_potion",
    "regen_potion",
    "explosive_potion",
    "ancient_potion",
}


def validate_potions_db(potions: dict = None):
    potions = POTIONS_DB if potions is None else potions
    if not isinstance(potions, dict) or not potions:
        raise ValueError("Potion data must be a non-empty object")
    for potion_id, potion in potions.items():
        if not isinstance(potion, dict):
            raise ValueError(f"Potion {potion_id} must be an object")
        if potion.get("id") != potion_id:
            raise ValueError(f"Potion {potion_id} id does not match its key")
        for field, expected_type in POTION_REQUIRED_FIELDS.items():
            if not isinstance(potion.get(field), expected_type) or not potion.get(field):
                raise ValueError(f"Potion {potion_id} has invalid {field}")
        if potion_id not in IMPLEMENTED_POTION_IDS:
            raise ValueError(f"Potion {potion_id} has no use implementation")


def load_potions_db(filepath="data/potions.json"):
    if not os.path.exists(filepath):
        data = deepcopy(DEFAULT_POTIONS_DB)
    else:
        with open(filepath, "r", encoding="utf-8") as potion_file:
            data = json.load(potion_file)
    validate_potions_db(data)
    return data


def _select_enemy(game, target_index: int):
    if 0 <= target_index < len(game.enemies):
        candidate = game.enemies[target_index]
        if not candidate.is_dead():
            return candidate
    return next((enemy for enemy in game.enemies if not enemy.is_dead()), None)


def use_potion(potion_id: str, game, target_index: int = 0) -> bool:
    if potion_id not in POTIONS_DB:
        return False

    if potion_id == "fire_potion":
        target = _select_enemy(game, target_index)
        if not target:
            return False
        target.take_damage(20)
        print(f"> Fire Potion deals 20 damage to {target.name}!")
    elif potion_id == "weak_potion":
        target = _select_enemy(game, target_index)
        if not target:
            return False
        target.apply_buff("weak", 3)
        print(f"> Weak Potion applies 3 Weak to {target.name}!")
    elif potion_id == "fear_potion":
        target = _select_enemy(game, target_index)
        if not target:
            return False
        target.apply_buff("vulnerable", 3)
        print(f"> Fear Potion applies 3 Vulnerable to {target.name}!")
    elif potion_id == "swift_potion":
        game.draw_cards(3)
        print("> Swift Potion draws 3 cards!")
    elif potion_id == "blood_potion":
        game.player.heal(game.player.max_hp // 4)
        print(f"> Blood Potion heals {game.player.max_hp // 4} HP!")
    elif potion_id == "block_potion":
        game.player.add_block(12)
        print("> Block Potion grants 12 block!")
    elif potion_id == "strength_potion":
        game.player.apply_buff("strength", 2)
        print("> Strength Potion grants 2 strength!")
    elif potion_id == "dexterity_potion":
        game.player.apply_buff("dexterity", 2)
        print("> Dexterity Potion grants 2 dexterity!")
    elif potion_id == "energy_potion":
        game.player.energy += 2
        print("> Energy Potion grants 2 energy!")
    elif potion_id == "regen_potion":
        game.player.apply_buff("regen", 5)
        print("> Regeneration Potion grants 5 Regen!")
    elif potion_id == "explosive_potion":
        for enemy in game.enemies:
            if not enemy.is_dead():
                enemy.take_damage(10)
        print("> Explosive Potion deals 10 damage to all enemies!")
    elif potion_id == "ancient_potion":
        game.player.apply_buff("artifact", 1)
        print("> Ancient Potion grants 1 Artifact!")
    else:
        return False

    return True


POTIONS_DB = load_potions_db()
