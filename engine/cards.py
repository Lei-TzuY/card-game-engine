import random
from copy import deepcopy
from typing import List

class Card:
    def __init__(
        self,
        card_id: str,
        name: str,
        cost: int,
        card_type: str,
        effects: List[dict],
        exhaust: bool = False,
        upgrade: dict = None,
        upgraded: bool = False,
        rarity: str = "common",
    ):
        self.id = card_id
        self.name = name
        self.cost = cost
        self.type = card_type
        self.effects = deepcopy(effects)
        self.exhaust = exhaust
        self.upgrade = deepcopy(upgrade) if upgrade else None
        self.upgraded = upgraded
        self.rarity = rarity

    def copy(self):
        return Card(
            self.id,
            self.name,
            self.cost,
            self.type,
            self.effects,
            exhaust=self.exhaust,
            upgrade=self.upgrade,
            upgraded=self.upgraded,
            rarity=self.rarity,
        )

    def upgraded_copy(self):
        if not self.upgrade or self.upgraded:
            return self.copy()
        return Card(
            f"{self.id}+",
            f"{self.name}+",
            self.upgrade.get("cost", self.cost),
            self.type,
            self.upgrade.get("effects", self.effects),
            exhaust=self.upgrade.get("exhaust", self.exhaust),
            upgraded=True,
            rarity=self.rarity,
        )

    def __str__(self):
        return f"[{self.cost}] {self.name} ({self.type})"

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "cost": self.cost,
            "type": self.type,
            "effects": self.effects,
            "exhaust": self.exhaust,
            "upgraded": self.upgraded,
            "upgradeable": bool(self.upgrade) and not self.upgraded,
            "rarity": self.rarity,
        }

class CardPile:
    def __init__(self, cards: List[Card] = None):
        self.cards = cards if cards is not None else []

    def add(self, card: Card):
        self.cards.append(card)

    def draw(self) -> Card:
        if self.is_empty():
            return None
        return self.cards.pop()

    def shuffle(self):
        random.shuffle(self.cards)

    def is_empty(self) -> bool:
        return len(self.cards) == 0

    def get_all(self) -> List[Card]:
        return self.cards

    def clear(self):
        self.cards.clear()

    def __len__(self):
        return len(self.cards)
