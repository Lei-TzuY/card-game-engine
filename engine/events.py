import json
import os
import random
from copy import deepcopy

from engine.potions import POTIONS_DB


DEFAULT_EVENTS_DB = {
    "healing_spring": {
        "id": "healing_spring",
        "name": "Healing Spring",
        "description": "Clear water bubbles up from a quiet stone basin.",
        "choices": [
            {
                "id": "drink",
                "label": "Drink",
                "description": "Heal 20% of your maximum HP.",
                "action": {"type": "heal_percent", "amount": 20},
            },
            {
                "id": "leave",
                "label": "Leave",
                "description": "Continue without drinking.",
                "action": {"type": "leave"},
            },
        ],
    },
    "golden_idol": {
        "id": "golden_idol",
        "name": "Golden Idol",
        "description": "A valuable idol rests behind a line of sharpened stones.",
        "choices": [
            {
                "id": "take",
                "label": "Take the Idol",
                "description": "Lose 7 HP. Gain 100 gold.",
                "action": {"type": "gold_for_hp", "hp": 7, "gold": 100},
            },
            {
                "id": "leave",
                "label": "Leave",
                "description": "Avoid the trap.",
                "action": {"type": "leave"},
            },
        ],
    },
    "potion_lab": {
        "id": "potion_lab",
        "name": "Abandoned Laboratory",
        "description": "One intact potion remains among the broken glass.",
        "choices": [
            {
                "id": "search",
                "label": "Search the Shelves",
                "description": "Gain a random potion. Gain 30 gold instead if your slots are full.",
                "action": {"type": "gain_potion", "fallback_gold": 30},
            },
            {
                "id": "leave",
                "label": "Leave",
                "description": "Do not disturb the laboratory.",
                "action": {"type": "leave"},
            },
        ],
    },
    "the_cleric": {
        "id": "the_cleric",
        "name": "The Cleric",
        "description": "A man in strange garb offers you his services.",
        "choices": [
            {
                "id": "heal",
                "label": "Heal",
                "description": "Heal 25% of your Max HP. Lose 35 Gold.",
                "action": {"type": "heal_percent_cost_gold", "amount": 25, "gold": 35},
            },
            {
                "id": "purify",
                "label": "Purify",
                "description": "Remove a random Strike or Defend from your deck. Lose 50 Gold.",
                "action": {"type": "remove_random_basic_cost_gold", "gold": 50},
            },
            {
                "id": "leave",
                "label": "Leave",
                "description": "Leave the Cleric.",
                "action": {"type": "leave"},
            },
        ],
    },
    "scrap_ooze": {
        "id": "scrap_ooze",
        "name": "Scrap Ooze",
        "description": "A pile of metallic sludge holds a shiny object. Reaching in will hurt.",
        "choices": [
            {
                "id": "reach",
                "label": "Reach Inside",
                "description": "Take 10 damage to gain a random Relic.",
                "action": {"type": "damage_for_relic", "damage": 10},
            },
            {
                "id": "leave",
                "label": "Leave",
                "description": "Leave it alone.",
                "action": {"type": "leave"},
            },
        ],
    },
    "vampires": {
        "id": "vampires",
        "name": "Vampires(?)",
        "description": "A group of hooded figures offer you a cup of dark blood.",
        "choices": [
            {
                "id": "accept",
                "label": "Accept",
                "description": "Lose 30% Max HP. Replace all Strikes with Bites.",
                "action": {"type": "become_vampire"},
            },
            {
                "id": "leave",
                "label": "Refuse",
                "description": "Politely decline.",
                "action": {"type": "leave"},
            },
        ],
    },
    "mysterious_sphere": {
        "id": "mysterious_sphere",
        "name": "Mysterious Sphere",
        "description": "A humming metal sphere splits open along a seam. Something glints inside.",
        "choices": [
            {
                "id": "reach",
                "label": "Reach Inside",
                "description": "Take 10 damage to gain a random Relic.",
                "action": {"type": "damage_for_relic", "damage": 10},
            },
            {
                "id": "leave",
                "label": "Leave",
                "description": "Back away slowly.",
                "action": {"type": "leave"},
            },
        ],
    },
    "fountain_of_purity": {
        "id": "fountain_of_purity",
        "name": "Fountain of Purity",
        "description": "A crystalline fountain pours endlessly into a basin of light.",
        "choices": [
            {
                "id": "drink",
                "label": "Drink Deeply",
                "description": "Heal 30% of your maximum HP.",
                "action": {"type": "heal_percent", "amount": 30},
            },
            {
                "id": "leave",
                "label": "Leave",
                "description": "Continue on your way.",
                "action": {"type": "leave"},
            },
        ],
    },
    "wandering_merchant": {
        "id": "wandering_merchant",
        "name": "Wandering Merchant",
        "description": "A cloaked figure sets down a heavy pack and offers a few odd services.",
        "choices": [
            {
                "id": "heal",
                "label": "Field Medicine",
                "description": "Heal 25% of your Max HP. Lose 40 Gold.",
                "action": {"type": "heal_percent_cost_gold", "amount": 25, "gold": 40},
            },
            {
                "id": "search",
                "label": "Rummage the Pack",
                "description": "Gain a random potion. Gain 25 gold instead if your slots are full.",
                "action": {"type": "gain_potion", "fallback_gold": 25},
            },
            {
                "id": "leave",
                "label": "Leave",
                "description": "Decline and move on.",
                "action": {"type": "leave"},
            },
        ],
    },
    "bonfire_spirits": {
        "id": "bonfire_spirits",
        "name": "Bonfire Spirits",
        "description": "Playful spirits dance around a roaring bonfire, beckoning for an offering.",
        "choices": [
            {
                "id": "offer",
                "label": "Offer a Basic Card",
                "description": "Remove a random Strike or Defend from your deck.",
                "action": {"type": "remove_random_basic_cost_gold", "gold": 0},
            },
            {
                "id": "leave",
                "label": "Leave",
                "description": "Warm your hands and move on.",
                "action": {"type": "leave"},
            },
        ],
    },
    "forgotten_cache": {
        "id": "forgotten_cache",
        "name": "Forgotten Cache",
        "description": "A cracked lockbox sits half-buried beneath old battlefield ash.",
        "choices": [
            {
                "id": "force",
                "label": "Force It Open",
                "description": "Lose 6 HP. Gain 80 gold.",
                "action": {"type": "gold_for_hp", "hp": 6, "gold": 80},
            },
            {
                "id": "leave",
                "label": "Leave",
                "description": "Leave the lockbox untouched.",
                "action": {"type": "leave"},
            },
        ],
    },
    "field_surgeon": {
        "id": "field_surgeon",
        "name": "Field Surgeon",
        "description": "A tired medic offers quick treatment before the road turns dangerous.",
        "choices": [
            {
                "id": "patch_up",
                "label": "Patch Up",
                "description": "Heal 20% of your Max HP. Lose 25 Gold.",
                "action": {"type": "heal_percent_cost_gold", "amount": 20, "gold": 25},
            },
            {
                "id": "cleanse",
                "label": "Cleanse Supplies",
                "description": "Remove a random Strike or Defend from your deck. Lose 60 Gold.",
                "action": {"type": "remove_random_basic_cost_gold", "gold": 60},
            },
            {
                "id": "leave",
                "label": "Leave",
                "description": "Thank the medic and move on.",
                "action": {"type": "leave"},
            },
        ],
    },
    "sealed_chest": {
        "id": "sealed_chest",
        "name": "Sealed Chest",
        "description": "A heavy chest hums with pressure whenever you touch the latch.",
        "choices": [
            {
                "id": "open",
                "label": "Open It",
                "description": "Take 12 damage to gain a random Relic.",
                "action": {"type": "damage_for_relic", "damage": 12},
            },
            {
                "id": "leave",
                "label": "Leave",
                "description": "The chest can keep its secret.",
                "action": {"type": "leave"},
            },
        ],
    },
}

EVENT_REQUIRED_FIELDS = {
    "id": str,
    "name": str,
    "description": str,
    "choices": list,
}
CHOICE_REQUIRED_FIELDS = {
    "id": str,
    "label": str,
    "description": str,
    "action": dict,
}
EVENT_ACTION_REQUIREMENTS = {
    "become_vampire": {},
    "damage_for_relic": {"damage": int},
    "gain_potion": {"fallback_gold": int},
    "gold_for_hp": {"hp": int, "gold": int},
    "heal_percent": {"amount": int},
    "heal_percent_cost_gold": {"amount": int, "gold": int},
    "leave": {},
    "remove_random_basic_cost_gold": {"gold": int},
}


def validate_events_db(events: dict = None):
    events = EVENTS_DB if events is None else events
    if not isinstance(events, dict) or not events:
        raise ValueError("Event data must be a non-empty object")
    for event_id, event in events.items():
        _validate_event(event_id, event)


def _validate_event(event_id: str, event: dict):
    if not isinstance(event, dict):
        raise ValueError(f"Event {event_id} must be an object")
    if event.get("id") != event_id:
        raise ValueError(f"Event {event_id} id does not match its key")
    for field, expected_type in EVENT_REQUIRED_FIELDS.items():
        if not isinstance(event.get(field), expected_type) or (expected_type is str and not event.get(field)):
            raise ValueError(f"Event {event_id} has invalid {field}")
    if not event["choices"]:
        raise ValueError(f"Event {event_id} must define at least one choice")
    choice_ids = set()
    for choice in event["choices"]:
        _validate_choice(event_id, choice, choice_ids)


def _validate_choice(event_id: str, choice: dict, choice_ids: set):
    if not isinstance(choice, dict):
        raise ValueError(f"Event {event_id} has invalid choice")
    for field, expected_type in CHOICE_REQUIRED_FIELDS.items():
        if not isinstance(choice.get(field), expected_type) or (expected_type is str and not choice.get(field)):
            raise ValueError(f"Event {event_id} choice has invalid {field}")
    if choice["id"] in choice_ids:
        raise ValueError(f"Event {event_id} has duplicate choice id: {choice['id']}")
    choice_ids.add(choice["id"])
    _validate_event_action(event_id, choice["id"], choice["action"])


def _validate_event_action(event_id: str, choice_id: str, action: dict):
    action_type = action.get("type")
    requirements = EVENT_ACTION_REQUIREMENTS.get(action_type)
    if requirements is None:
        raise ValueError(f"Event {event_id} choice {choice_id} has unsupported action type: {action_type}")
    for field, expected_type in requirements.items():
        if not isinstance(action.get(field), expected_type):
            raise ValueError(f"Event {event_id} choice {choice_id} has invalid action {field}")


def load_events_db(filepath="data/events.json"):
    if not os.path.exists(filepath):
        data = deepcopy(DEFAULT_EVENTS_DB)
    else:
        with open(filepath, "r", encoding="utf-8") as event_file:
            data = json.load(event_file)
    validate_events_db(data)
    return data


EVENTS_DB = load_events_db()


def event_to_dict(event_id: str):
    event = EVENTS_DB.get(event_id)
    if not event:
        return None
    return {
        "id": event["id"],
        "name": event["name"],
        "description": event["description"],
        "choices": [
            {
                "id": choice["id"],
                "label": choice["label"],
                "description": choice["description"],
            }
            for choice in event["choices"]
        ],
    }


def apply_event_choice(session, event_id: str, choice_id: str) -> bool:
    event = EVENTS_DB.get(event_id)
    if not event:
        return False
    choice = next((item for item in event["choices"] if item["id"] == choice_id), None)
    if not choice:
        return False

    action = choice["action"]
    action_type = action["type"]
    if action_type == "heal_percent":
        session.player.heal(session.player.max_hp * action["amount"] // 100)
    elif action_type == "gold_for_hp":
        session.player.lose_hp(action["hp"])
        session.gold += action["gold"]
    elif action_type == "gain_potion":
        if len(session.potions) < session.max_potion_slots:
            session.potions.append(random.choice(list(POTIONS_DB)))
        else:
            session.gold += action["fallback_gold"]
    elif action_type == "heal_percent_cost_gold":
        if session.gold >= action["gold"]:
            session.gold -= action["gold"]
            session.player.heal(session.player.max_hp * action["amount"] // 100)
        else:
            return False
    elif action_type == "remove_random_basic_cost_gold":
        if session.gold >= action["gold"]:
            basics = [i for i, card in enumerate(session.master_deck) if card.startswith("strike") or card.startswith("defend")]
            if basics:
                session.gold -= action["gold"]
                session.master_deck.pop(random.choice(basics))
            else:
                return False
        else:
            return False
    elif action_type == "damage_for_relic":
        from engine.relics import get_relic_reward_pool
        session.player.lose_hp(action["damage"]) # Event damage shouldn't trigger block, usually
        pool = get_relic_reward_pool(session.relics)
        if pool:
            session.relics.append(random.choice(pool))
    elif action_type == "become_vampire":
        session.player.max_hp = int(session.player.max_hp * 0.7)
        if session.player.hp > session.player.max_hp:
            session.player.hp = session.player.max_hp
        for i in range(len(session.master_deck)):
            if session.master_deck[i].startswith("strike"):
                session.master_deck[i] = "bite" + ("+" if session.master_deck[i].endswith("+") else "")

    return True
