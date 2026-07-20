import json
from typing import Dict, List
from engine.cards import Card

CARD_REQUIRED_FIELDS = {
    "id": str,
    "name": str,
    "cost": int,
    "type": str,
    "effects": list,
}
CARD_TYPES = {"Attack", "Skill", "Power"}
CARD_RARITIES = {"common", "uncommon", "rare"}
DEFAULT_RARITY = "common"
X_COST = "X"


def _valid_cost(value) -> bool:
    return value == X_COST or (isinstance(value, int) and not isinstance(value, bool) and value >= 0)
EFFECT_TYPES = {
    "apply_buff",
    "block",
    "block_damage",
    "change_stance",
    "channel_orb",
    "damage",
    "double_block",
    "draw",
    "evoke_orb",
    "gain_energy",
    "heal",
    "poison",
    "remove_buff",
}


class CardDatabase:
    def __init__(self):
        self.cards: Dict[str, Card] = {}

    def load_from_file(self, filepath: str):
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        self.load_from_data(data)

    def load_from_data(self, data: list):
        if not isinstance(data, list):
            raise ValueError("Card data must be a list")

        loaded_cards = {}
        for card_data in data:
            self._validate_card_data(card_data)
            card_id = card_data["id"]
            if card_id in loaded_cards:
                raise ValueError(f"Duplicate card id: {card_id}")

            card = Card(
                card_id=card_id,
                name=card_data["name"],
                cost=card_data["cost"],
                card_type=card_data["type"],
                effects=card_data["effects"],
                exhaust=card_data.get("exhaust", False),
                upgrade=card_data.get("upgrade"),
                rarity=card_data.get("rarity", DEFAULT_RARITY),
            )
            loaded_cards[card.id] = card

        self.cards = loaded_cards

    def _validate_card_data(self, card_data: dict):
        if not isinstance(card_data, dict):
            raise ValueError("Each card must be an object")
        for field, expected_type in CARD_REQUIRED_FIELDS.items():
            if field == "cost":
                continue  # cost may be an int or the string "X"; checked below
            if not isinstance(card_data.get(field), expected_type):
                raise ValueError(f"Card has invalid {field}")
        if not _valid_cost(card_data.get("cost")):
            raise ValueError(f"Card {card_data.get('id')} has invalid cost")
        if not card_data["id"]:
            raise ValueError("Card id cannot be empty")
        if card_data["type"] not in CARD_TYPES:
            raise ValueError(f"Card {card_data['id']} has invalid type")
        if card_data.get("rarity", DEFAULT_RARITY) not in CARD_RARITIES:
            raise ValueError(f"Card {card_data['id']} has invalid rarity")
        self._validate_effects(card_data["id"], card_data["effects"])
        upgrade = card_data.get("upgrade")
        if upgrade is not None and not isinstance(upgrade, dict):
            raise ValueError(f"Card {card_data['id']} has invalid upgrade")
        if upgrade and "cost" in upgrade and not _valid_cost(upgrade["cost"]):
            raise ValueError(f"Card {card_data['id']} has invalid upgrade cost")
        if upgrade and "effects" in upgrade and not isinstance(upgrade["effects"], list):
            raise ValueError(f"Card {card_data['id']} has invalid upgrade effects")
        if upgrade and "effects" in upgrade:
            self._validate_effects(card_data["id"], upgrade["effects"])

    def _validate_effects(self, card_id: str, effects: list):
        for effect in effects:
            if not isinstance(effect, dict):
                raise ValueError(f"Card {card_id} has invalid effect")
            effect_type = effect.get("type")
            if effect_type not in EFFECT_TYPES:
                raise ValueError(f"Card {card_id} has unsupported effect type: {effect_type}")

    def get_card(self, card_id: str) -> Card:
        upgraded = card_id.endswith("+")
        base_id = card_id[:-1] if upgraded else card_id
        base_card = self.cards.get(base_id)
        if base_card:
            return base_card.upgraded_copy() if upgraded else base_card.copy()
        return None

    def can_upgrade(self, card_id: str) -> bool:
        return not card_id.endswith("+") and bool(self.cards.get(card_id) and self.cards[card_id].upgrade)

    def to_dict(self) -> Dict[str, dict]:
        result = {}
        for card_id, card in self.cards.items():
            result[card_id] = card.to_dict()
            if card.upgrade:
                upgraded = card.upgraded_copy()
                result[upgraded.id] = upgraded.to_dict()
        return result


def load_card_rarities(filepath: str = "data/cards.json") -> Dict[str, str]:
    """Module-level lookup of base card id -> rarity, for reward weighting."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}
    rarities = {}
    for card_data in data:
        if isinstance(card_data, dict) and card_data.get("id"):
            rarities[card_data["id"]] = card_data.get("rarity", DEFAULT_RARITY)
    return rarities


CARD_RARITY_BY_ID = load_card_rarities()


def card_rarity(card_id: str) -> str:
    base_id = card_id[:-1] if card_id.endswith("+") else card_id
    return CARD_RARITY_BY_ID.get(base_id, DEFAULT_RARITY)
