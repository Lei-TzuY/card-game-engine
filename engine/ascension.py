"""Ascension difficulty tiers and the run modifiers each level applies.

Levels are cumulative: at ascension N, every effect for levels <= N is active.
Higher levels are unlocked by winning a run at the level below (see engine.meta).
"""

MAX_ASCENSION = 5

# One human-readable line per level, describing the *additional* effect it adds.
ASCENSION_EFFECTS = {
    1: "Enemies have +10% HP.",
    2: "Elites and Bosses have an additional +10% HP.",
    3: "You begin each run at 90% HP.",
    4: "Rest sites heal less (25% instead of 30%).",
    5: "You start with less gold (74 instead of 99).",
}

BASE_STARTING_GOLD = 99
LOW_STARTING_GOLD = 74
BASE_REST_HEAL_FRACTION = 0.30
LOW_REST_HEAL_FRACTION = 0.25


def clamp_ascension(level) -> int:
    if not isinstance(level, int) or isinstance(level, bool):
        return 0
    return max(0, min(MAX_ASCENSION, level))


def enemy_hp_multiplier(ascension: int, tier: str) -> float:
    multiplier = 1.0
    if ascension >= 1:
        multiplier *= 1.10
    if ascension >= 2 and tier in ("elite", "boss"):
        multiplier *= 1.10
    return multiplier


def scale_enemy_hp(hp: int, ascension: int, tier: str) -> int:
    if ascension <= 0:
        return hp
    scaled = int(round(hp * enemy_hp_multiplier(ascension, tier)))
    return max(1, scaled)


def starting_hp_fraction(ascension: int) -> float:
    return 0.90 if ascension >= 3 else 1.0


def rest_heal_fraction(ascension: int) -> float:
    return LOW_REST_HEAL_FRACTION if ascension >= 4 else BASE_REST_HEAL_FRACTION


def starting_gold(ascension: int) -> int:
    return LOW_STARTING_GOLD if ascension >= 5 else BASE_STARTING_GOLD


def ascension_levels() -> list:
    """Describe every selectable level (0..MAX) for the character-select UI."""
    levels = [{"level": 0, "effects": [], "summary": "Base difficulty."}]
    for level in range(1, MAX_ASCENSION + 1):
        effects = [ASCENSION_EFFECTS[n] for n in range(1, level + 1)]
        levels.append({
            "level": level,
            "effects": effects,
            "summary": ASCENSION_EFFECTS[level],
        })
    return levels
