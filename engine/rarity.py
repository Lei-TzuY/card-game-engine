"""Rarity tiers and weighted selection shared by card and relic rewards."""

import random

RARITIES = ("common", "uncommon", "rare")
DEFAULT_RARITY = "common"

# Relative weights for a single reward roll. Higher = more likely.
CARD_RARITY_WEIGHTS = {"common": 65, "uncommon": 28, "rare": 7}
RELIC_RARITY_WEIGHTS = {"common": 50, "uncommon": 35, "rare": 15}


def rarity_weight(rarity: str, weights: dict) -> int:
    return weights.get(rarity, weights.get(DEFAULT_RARITY, 1))


def weighted_sample(items: list, weight_fn, k: int) -> list:
    """Pick up to k distinct items, weighted by weight_fn, without replacement."""
    pool = list(items)
    chosen = []
    while pool and len(chosen) < k:
        weights = [max(0, weight_fn(item)) for item in pool]
        total = sum(weights)
        if total <= 0:
            chosen.append(pool.pop(random.randrange(len(pool))))
            continue
        threshold = random.uniform(0, total)
        running = 0
        for index, weight in enumerate(weights):
            running += weight
            if running >= threshold:
                chosen.append(pool.pop(index))
                break
    return chosen


def weighted_choice(items: list, weight_fn):
    picks = weighted_sample(items, weight_fn, 1)
    return picks[0] if picks else None
