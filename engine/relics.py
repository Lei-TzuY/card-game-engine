import json
import os
from copy import deepcopy

from engine.rarity import (
    RARITIES,
    RELIC_RARITY_WEIGHTS,
    rarity_weight,
    weighted_choice,
)


DEFAULT_RELICS_DB = {
    "burning_blood": {
        "id": "burning_blood",
        "rarity": "common",
        "name": "Burning Blood",
        "description": "At the end of combat, heal 6 HP.",
        "icon": "BB",
        "rewardable": False,
    },
    "vajra": {
        "id": "vajra",
        "rarity": "uncommon",
        "name": "Vajra",
        "description": "At the start of each combat, gain 1 Strength.",
        "icon": "V",
        "rewardable": True,
    },
    "anchor": {
        "id": "anchor",
        "rarity": "common",
        "name": "Anchor",
        "description": "At the start of each combat, gain 10 Block.",
        "icon": "A",
        "rewardable": True,
    },
    "blood_vial": {
        "id": "blood_vial",
        "rarity": "common",
        "name": "Blood Vial",
        "description": "At the start of each combat, heal 2 HP.",
        "icon": "+",
        "rewardable": True,
    },
    "pure_water": {
        "id": "pure_water",
        "rarity": "common",
        "name": "Pure Water",
        "description": "At the start of each combat, gain 1 Energy.",
        "icon": "W",
        "rewardable": False,
    },
    "oddly_smooth_stone": {
        "id": "oddly_smooth_stone",
        "rarity": "common",
        "name": "Oddly Smooth Stone",
        "description": "At the start of each combat, gain 1 Dexterity (Block Buff).",
        "icon": "D",
        "rewardable": True,
    },
    "pen_nib": {
        "id": "pen_nib",
        "rarity": "uncommon",
        "name": "Pen Nib",
        "description": "Every 10th Attack you play deals double damage.",
        "icon": "PN",
        "rewardable": True,
    },
    "orichalcum": {
        "id": "orichalcum",
        "rarity": "uncommon",
        "name": "Orichalcum",
        "description": "If you end your turn without Block, gain 6 Block.",
        "icon": "O",
        "rewardable": True,
    },
    "tungsten_rod": {
        "id": "tungsten_rod",
        "rarity": "uncommon",
        "name": "Tungsten Rod",
        "description": "Whenever you lose HP, lose 1 less.",
        "icon": "TR",
        "rewardable": True,
    },
    "bag_of_marbles": {
        "id": "bag_of_marbles",
        "rarity": "common",
        "name": "Bag of Marbles",
        "description": "At the start of each combat, apply 1 Vulnerable to ALL enemies.",
        "icon": "BM",
        "rewardable": True,
    },
    "bag_of_preparation": {
        "id": "bag_of_preparation",
        "rarity": "common",
        "name": "Bag of Preparation",
        "description": "At the start of each combat, draw 2 additional cards.",
        "icon": "BP",
        "rewardable": True,
    },
    "kunai": {
        "id": "kunai",
        "rarity": "uncommon",
        "name": "Kunai",
        "description": "Every 3rd Attack you play grants 1 Dexterity.",
        "icon": "KU",
        "rewardable": True,
    },
    "shuriken": {
        "id": "shuriken",
        "rarity": "uncommon",
        "name": "Shuriken",
        "description": "Every 3rd Attack you play grants 1 Strength.",
        "icon": "SH",
        "rewardable": True,
    },
    "letter_opener": {
        "id": "letter_opener",
        "rarity": "uncommon",
        "name": "Letter Opener",
        "description": "Every 3rd Skill you play deals 5 damage to ALL enemies.",
        "icon": "LO",
        "rewardable": True,
    },
    "meat_on_the_bone": {
        "id": "meat_on_the_bone",
        "rarity": "rare",
        "name": "Meat on the Bone",
        "description": "At the end of combat, if your HP is at or below 50%, heal 12 HP.",
        "icon": "MB",
        "rewardable": True,
    },
    "lantern": {
        "id": "lantern",
        "rarity": "uncommon",
        "name": "Lantern",
        "description": "At the start of each combat, gain 1 Energy.",
        "icon": "LA",
        "rewardable": True,
    },
    "thread_and_needle": {
        "id": "thread_and_needle",
        "rarity": "rare",
        "name": "Thread and Needle",
        "description": "At the start of each combat, gain 4 Block.",
        "icon": "TN",
        "rewardable": True,
    },
    "mercury_hourglass": {
        "id": "mercury_hourglass",
        "rarity": "uncommon",
        "name": "Mercury Hourglass",
        "description": "At the end of your turn, deal 3 damage to ALL enemies.",
        "icon": "MH",
        "rewardable": True,
    },
    "bronze_scales": {
        "id": "bronze_scales",
        "rarity": "uncommon",
        "name": "Bronze Scales",
        "description": "At the start of each combat, gain 3 Thorns.",
        "icon": "BS",
        "rewardable": True,
    },
    "red_skull": {
        "id": "red_skull",
        "rarity": "uncommon",
        "name": "Red Skull",
        "description": "At the start of each combat, if your HP is at or below 50%, gain 3 Strength.",
        "icon": "RS",
        "rewardable": True,
    },
    "red_mask": {
        "id": "red_mask",
        "rarity": "uncommon",
        "name": "Red Mask",
        "description": "At the start of each combat, apply 1 Weak to ALL enemies.",
        "icon": "RM",
        "rewardable": True,
    },
}

RELIC_REQUIRED_FIELDS = {
    "id": str,
    "name": str,
    "description": str,
    "icon": str,
    "rewardable": bool,
}
IMPLEMENTED_RELIC_IDS = {
    "anchor",
    "bag_of_marbles",
    "bag_of_preparation",
    "blood_vial",
    "bronze_scales",
    "burning_blood",
    "kunai",
    "letter_opener",
    "lantern",
    "meat_on_the_bone",
    "mercury_hourglass",
    "oddly_smooth_stone",
    "orichalcum",
    "pen_nib",
    "pure_water",
    "red_mask",
    "red_skull",
    "shuriken",
    "thread_and_needle",
    "tungsten_rod",
    "vajra",
}


def validate_relics_db(relics: dict = None):
    relics = RELICS_DB if relics is None else relics
    if not isinstance(relics, dict) or not relics:
        raise ValueError("Relic data must be a non-empty object")
    for relic_id, relic in relics.items():
        if not isinstance(relic, dict):
            raise ValueError(f"Relic {relic_id} must be an object")
        if relic.get("id") != relic_id:
            raise ValueError(f"Relic {relic_id} id does not match its key")
        for field, expected_type in RELIC_REQUIRED_FIELDS.items():
            if not isinstance(relic.get(field), expected_type) or (expected_type is str and not relic.get(field)):
                raise ValueError(f"Relic {relic_id} has invalid {field}")
        if relic.get("rarity", "common") not in RARITIES:
            raise ValueError(f"Relic {relic_id} has invalid rarity")
        if relic_id not in IMPLEMENTED_RELIC_IDS:
            raise ValueError(f"Relic {relic_id} has no trigger implementation")


def load_relics_db(filepath="data/relics.json"):
    if not os.path.exists(filepath):
        data = deepcopy(DEFAULT_RELICS_DB)
    else:
        with open(filepath, "r", encoding="utf-8") as relic_file:
            data = json.load(relic_file)
    validate_relics_db(data)
    return data


RELICS_DB = load_relics_db()


def get_relic_reward_pool(owned_relics: list) -> list:
    return [
        relic_id
        for relic_id, relic in RELICS_DB.items()
        if relic.get("rewardable") and relic_id not in owned_relics
    ]


def relic_rarity(relic_id: str) -> str:
    relic = RELICS_DB.get(relic_id, {})
    return relic.get("rarity", "common")


def roll_relic_reward(owned_relics: list):
    """Pick a single rewardable relic, weighted by rarity."""
    pool = get_relic_reward_pool(owned_relics)
    return weighted_choice(
        pool,
        lambda relic_id: rarity_weight(relic_rarity(relic_id), RELIC_RARITY_WEIGHTS),
    )


def trigger_relic_on_combat_start(relic_id: str, game):
    if relic_id == "vajra":
        game.player.apply_buff("strength", 1)
        print("> Vajra activates: Gained 1 Strength!")
    elif relic_id == "anchor":
        game.player.add_block(10)
        print("> Anchor activates: Gained 10 Block!")
    elif relic_id == "blood_vial":
        game.player.heal(2)
        print("> Blood Vial activates: Healed 2 HP!")
    elif relic_id == "pure_water":
        game.player.energy += 1
        print("> Pure Water activates: Gained 1 Energy for this turn!")
    elif relic_id == "oddly_smooth_stone":
        game.player.apply_buff("dexterity", 1)
        print("> Oddly Smooth Stone activates: Gained 1 Dexterity!")
    elif relic_id == "bag_of_marbles":
        for enemy in game.enemies:
            if not enemy.is_dead():
                enemy.apply_buff("vulnerable", 1)
        print("> Bag of Marbles activates: All enemies are Vulnerable!")
    elif relic_id == "bag_of_preparation":
        game.draw_cards(2)
        print("> Bag of Preparation activates: Drew 2 extra cards!")
    elif relic_id == "bronze_scales":
        game.player.apply_buff("thorns", 3)
        print("> Bronze Scales activates: Gained 3 Thorns!")
    elif relic_id == "red_skull":
        if game.player.hp <= game.player.max_hp // 2:
            game.player.apply_buff("strength", 3)
            print("> Red Skull activates: Gained 3 Strength!")
    elif relic_id == "red_mask":
        for enemy in game.enemies:
            if not enemy.is_dead():
                enemy.apply_buff("weak", 1)
        print("> Red Mask activates: All enemies are Weakened!")
    elif relic_id == "lantern":
        game.player.energy += 1
        print("> Lantern activates: Gained 1 Energy for this turn!")
    elif relic_id == "thread_and_needle":
        game.player.add_block(4)
        print("> Thread and Needle activates: Gained 4 Block!")


def trigger_relic_on_combat_end(relic_id: str, session):
    if relic_id == "burning_blood":
        session.player.heal(6)
        print(f"> Burning Blood activates: Healed 6 HP. Current HP: {session.player.hp}")
    elif relic_id == "meat_on_the_bone":
        if session.player.hp <= session.player.max_hp // 2:
            session.player.heal(12)
            print(f"> Meat on the Bone activates: Healed 12 HP. Current HP: {session.player.hp}")


def _tick_every_third(game, counter_name: str) -> bool:
    """Increment a hidden counter buff and return True every 3rd call."""
    count = game.player.get_buff(counter_name) + 1
    if count >= 3:
        game.player.buffs[counter_name] = 0
        return True
    game.player.buffs[counter_name] = count
    return False


def trigger_relic_on_card_play(relic_id: str, game, card):
    if relic_id == "pen_nib" and card.type == "Attack":
        count = game.player.get_buff("pen_nib_counter") + 1
        if count >= 10:
            game.player.buffs["pen_nib_counter"] = 0
            game.player.apply_buff("pen_nib_active", 1)
            print("> Pen Nib activates! Next attack deals double damage!")
        else:
            game.player.buffs["pen_nib_counter"] = count
    elif relic_id == "kunai" and card.type == "Attack":
        if _tick_every_third(game, "kunai_counter"):
            game.player.apply_buff("dexterity", 1)
            print("> Kunai activates: Gained 1 Dexterity!")
    elif relic_id == "shuriken" and card.type == "Attack":
        if _tick_every_third(game, "shuriken_counter"):
            game.player.apply_buff("strength", 1)
            print("> Shuriken activates: Gained 1 Strength!")
    elif relic_id == "letter_opener" and card.type == "Skill":
        if _tick_every_third(game, "letter_opener_counter"):
            for enemy in game.enemies:
                if not enemy.is_dead():
                    enemy.take_damage(5)
            print("> Letter Opener activates: 5 damage to all enemies!")


def trigger_relic_on_turn_end(relic_id: str, game):
    if relic_id == "orichalcum" and game.player.block == 0:
        game.player.add_block(6)
        print("> Orichalcum activates: Gained 6 Block!")
    elif relic_id == "mercury_hourglass":
        for enemy in game.enemies:
            if not enemy.is_dead():
                enemy.take_damage(3)
        print("> Mercury Hourglass activates: 3 damage to all enemies!")


def trigger_relic_on_take_damage(relic_id: str, game, amount: int) -> int:
    if relic_id == "tungsten_rod" and amount > 0:
        print("> Tungsten Rod activates: Reduced HP loss by 1!")
        return amount - 1
    return amount
