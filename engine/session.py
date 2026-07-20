import os
import json
import random
from datetime import datetime, timezone
from copy import deepcopy
from engine.ascension import (
    MAX_ASCENSION,
    clamp_ascension,
    rest_heal_fraction,
    scale_enemy_hp,
    starting_gold,
)
from engine.database import card_rarity
from engine.entities import Player
from engine.events import EVENTS_DB, apply_event_choice, event_to_dict
from engine.potions import POTIONS_DB, use_potion
from engine.rarity import CARD_RARITY_WEIGHTS, rarity_weight, weighted_sample
from engine.relics import RELICS_DB, roll_relic_reward, trigger_relic_on_combat_end
from engine.characters import get_character

SAVE_VERSION = 6
SHOP_CARD_COUNT = 3
SHOP_CARD_PRICE = 50
SHOP_CARD_PRICES = {"common": 50, "uncommon": 75, "rare": 150}
SHOP_POTION_COUNT = 2
SHOP_POTION_PRICE = 40
SHOP_REMOVE_PRICE = 75
MAX_POTION_SLOTS = 3
POTION_DROP_CHANCE = 0.4
SAVE_BACKUP_SUFFIX = ".bak"
SAVE_TEMP_SUFFIX = ".tmp"

COMBAT_NODE_TYPES = {"Enemy", "Elite", "Boss"}
MAP_NODE_TYPES = COMBAT_NODE_TYPES | {"Event", "Rest", "Shop"}
SESSION_PHASES = {"CHARACTER_SELECT", "MAP", "COMBAT", "REWARD", "REST", "SHOP", "EVENT", "GAME_OVER"}
ENEMY_TIERS = {"easy", "normal", "elite", "boss"}
ENEMY_ACTION_REQUIREMENTS = {
    "attack": {"amount": int},
    "block": {"amount": int},
    "sleep": {},
    "strength": {"amount": int},
    "buff": {"amount": int, "buff": str},
    "debuff": {"amount": int, "buff": str},
}
ENEMY_SELF_BUFFS = {"strength", "dexterity", "ritual", "thorns", "metallicize", "regen", "artifact", "intangible"}
ENEMY_PLAYER_DEBUFFS = {"weak", "vulnerable", "frail"}
IMPLEMENTED_ENEMY_PASSIVES = {"Asleep", "Enrage"}
DEFAULT_ENEMY_TABLE = {
    "easy": [["Training Cultist", 20, [{"type": "attack", "amount": 5}]]],
    "normal": [["Training Brute", 40, [{"type": "attack", "amount": 8}, {"type": "block", "amount": 5}]]],
    "elite": [["Training Elite", 80, [{"type": "attack", "amount": 14}]]],
    "boss": [["Training Guardian", 180, [{"type": "attack", "amount": 18}], [{"threshold": 0.5, "name": "Guarded", "block": 12}]]],
}
ENEMY_TABLE = {}


def _card_weight(card_id: str) -> int:
    return rarity_weight(card_rarity(card_id), CARD_RARITY_WEIGHTS)


def sample_cards(pool: list, count: int) -> list:
    """Pick `count` distinct cards from a pool, weighted by rarity."""
    unique_pool = list(dict.fromkeys(pool))
    return weighted_sample(unique_pool, _card_weight, count)


def validate_enemy_db(enemy_db: dict = None):
    enemy_db = ENEMY_TABLE if enemy_db is None else enemy_db
    if not isinstance(enemy_db, dict) or not enemy_db:
        raise ValueError("Enemy data must be a non-empty object")
    missing_tiers = ENEMY_TIERS - set(enemy_db)
    if missing_tiers:
        raise ValueError(f"Enemy data is missing tiers: {', '.join(sorted(missing_tiers))}")
    for tier, enemies in enemy_db.items():
        if tier not in ENEMY_TIERS:
            raise ValueError(f"Enemy data has unsupported tier: {tier}")
        if not isinstance(enemies, list) or not enemies:
            raise ValueError(f"Enemy tier {tier} must be a non-empty list")
        for index, enemy_data in enumerate(enemies):
            _validate_enemy_entry(tier, index, enemy_data)


def _validate_enemy_entry(tier: str, index: int, enemy_data: list):
    label = f"{tier}[{index}]"
    if not isinstance(enemy_data, list) or not 3 <= len(enemy_data) <= 5:
        raise ValueError(f"Enemy {label} must be [name, hp, actions, phases?, passives?]")
    name, hp, actions = enemy_data[:3]
    if not isinstance(name, str) or not name:
        raise ValueError(f"Enemy {label} has invalid name")
    if not _is_positive_int(hp):
        raise ValueError(f"Enemy {label} has invalid hp")
    _validate_enemy_actions(label, actions)
    if len(enemy_data) > 3:
        _validate_enemy_phases(label, enemy_data[3])
    if len(enemy_data) > 4:
        _validate_enemy_passives(label, enemy_data[4])


def _validate_enemy_actions(label: str, actions: list):
    if not isinstance(actions, list) or not actions:
        raise ValueError(f"Enemy {label} must define at least one action")
    for action in actions:
        _validate_enemy_action(label, action)


def _validate_enemy_action(label: str, action: dict):
    if not isinstance(action, dict):
        raise ValueError(f"Enemy {label} has invalid action")
    action_type = action.get("type")
    requirements = ENEMY_ACTION_REQUIREMENTS.get(action_type)
    if requirements is None:
        raise ValueError(f"Enemy {label} has unsupported action type: {action_type}")
    for field, expected_type in requirements.items():
        if not isinstance(action.get(field), expected_type) or isinstance(action.get(field), bool):
            raise ValueError(f"Enemy {label} action {action_type} has invalid {field}")
        if field == "amount" and action[field] <= 0:
            raise ValueError(f"Enemy {label} action {action_type} amount must be positive")
        if field == "buff" and not action[field]:
            raise ValueError(f"Enemy {label} action {action_type} has empty buff")
    if action_type == "buff" and action["buff"] not in ENEMY_SELF_BUFFS:
        raise ValueError(f"Enemy {label} has unsupported self-buff: {action['buff']}")
    if action_type == "debuff" and action["buff"] not in ENEMY_PLAYER_DEBUFFS:
        raise ValueError(f"Enemy {label} has unsupported debuff: {action['buff']}")


def _validate_enemy_phases(label: str, phases: list):
    if phases in (None, []):
        return
    if not isinstance(phases, list):
        raise ValueError(f"Enemy {label} phases must be a list")
    previous_threshold = 1.01
    for phase_index, phase in enumerate(phases):
        phase_label = f"{label}.phases[{phase_index}]"
        if not isinstance(phase, dict):
            raise ValueError(f"Enemy {phase_label} must be an object")
        threshold = phase.get("threshold")
        if not isinstance(threshold, (int, float)) or isinstance(threshold, bool) or not 0 < threshold <= 1:
            raise ValueError(f"Enemy {phase_label} has invalid threshold")
        if threshold > previous_threshold:
            raise ValueError(f"Enemy {phase_label} thresholds must be descending")
        previous_threshold = threshold
        if "name" in phase and (not isinstance(phase["name"], str) or not phase["name"]):
            raise ValueError(f"Enemy {phase_label} has invalid name")
        if "actions" in phase:
            _validate_enemy_actions(phase_label, phase["actions"])
        for field in ("block", "strength"):
            if field in phase and not _is_positive_int(phase[field]):
                raise ValueError(f"Enemy {phase_label} has invalid {field}")


def _validate_enemy_passives(label: str, passives: list):
    if passives in (None, []):
        return
    if not isinstance(passives, list):
        raise ValueError(f"Enemy {label} passives must be a list")
    for passive in passives:
        if passive not in IMPLEMENTED_ENEMY_PASSIVES:
            raise ValueError(f"Enemy {label} has unsupported passive: {passive}")


def validate_enemy_instance(enemy: dict):
    if not isinstance(enemy, dict):
        raise ValueError("Map enemy must be an object")
    if not isinstance(enemy.get("name"), str) or not enemy.get("name"):
        raise ValueError("Map enemy has invalid name")
    if not _is_positive_int(enemy.get("hp")):
        raise ValueError(f"Map enemy {enemy.get('name')} has invalid hp")
    if "attack" in enemy and (not isinstance(enemy["attack"], int) or isinstance(enemy["attack"], bool) or enemy["attack"] < 0):
        raise ValueError(f"Map enemy {enemy['name']} has invalid attack")
    _validate_enemy_actions(enemy["name"], enemy.get("actions"))
    _validate_enemy_phases(enemy["name"], enemy.get("phases", []))
    _validate_enemy_passives(enemy["name"], enemy.get("passives", []))


def validate_map_nodes(nodes: list):
    if not isinstance(nodes, list) or not nodes:
        raise ValueError("Map nodes must be a non-empty list")
    ids = set()
    by_id = {}
    for node in nodes:
        if not isinstance(node, MapNode):
            raise ValueError("Map entries must be MapNode instances")
        if not isinstance(node.id, int) or node.id <= 0 or node.id in ids:
            raise ValueError(f"Map node has invalid id: {node.id}")
        if node.type not in MAP_NODE_TYPES:
            raise ValueError(f"Map node {node.id} has invalid type: {node.type}")
        if not isinstance(node.floor, int) or node.floor <= 0:
            raise ValueError(f"Map node {node.id} has invalid floor")
        if not isinstance(node.completed, bool):
            raise ValueError(f"Map node {node.id} has invalid completed state")
        if not isinstance(node.connections, list) or any(not isinstance(target_id, int) for target_id in node.connections):
            raise ValueError(f"Map node {node.id} has invalid connections")
        if node.type in COMBAT_NODE_TYPES:
            if not isinstance(node.enemies_data, list) or not node.enemies_data:
                raise ValueError(f"Map combat node {node.id} must include enemies")
            for enemy in node.enemies_data:
                validate_enemy_instance(enemy)
        elif node.enemies_data:
            raise ValueError(f"Map non-combat node {node.id} cannot include enemies")
        ids.add(node.id)
        by_id[node.id] = node

    for node in nodes:
        for target_id in node.connections:
            if target_id not in by_id:
                raise ValueError(f"Map node {node.id} connects to missing node {target_id}")
            if by_id[target_id].floor <= node.floor:
                raise ValueError(f"Map node {node.id} must connect to a later floor")


def validate_saved_session(session):
    if session.phase not in SESSION_PHASES:
        raise ValueError(f"Save data has invalid phase: {session.phase}")
    if not isinstance(session.floor, int) or isinstance(session.floor, bool) or session.floor < 0:
        raise ValueError("Save data has invalid floor")
    if not isinstance(session.gold, int) or isinstance(session.gold, bool) or session.gold < 0:
        raise ValueError("Save data has invalid gold")
    if not isinstance(session.ascension, int) or isinstance(session.ascension, bool) or not 0 <= session.ascension <= MAX_ASCENSION:
        raise ValueError("Save data has invalid ascension")
    if not _is_positive_int(session.max_potion_slots):
        raise ValueError("Save data has invalid max potion slots")
    if len(session.potions) > session.max_potion_slots:
        raise ValueError("Save data has too many potions")

    _validate_relic_ids(session.relics)
    _validate_potion_ids(session.potions)
    _validate_reward_state(session)
    _validate_shop_state(session)
    _validate_saved_map_state(session)


def _validate_saved_map_state(session):
    if not isinstance(session.map_nodes, list):
        raise ValueError("Save data has invalid map nodes")
    if not session.map_nodes:
        if session.current_node_id is not None:
            raise ValueError("Save data has current node without a map")
        if session.available_node_ids:
            raise ValueError("Save data has available nodes without a map")
        return

    validate_map_nodes(session.map_nodes)
    node_ids = {node.id for node in session.map_nodes}
    if session.current_node_id is not None and session.current_node_id not in node_ids:
        raise ValueError(f"Save data current node is missing from map: {session.current_node_id}")
    if not isinstance(session.available_node_ids, list):
        raise ValueError("Save data has invalid available nodes")
    for node_id in session.available_node_ids:
        if not isinstance(node_id, int) or isinstance(node_id, bool) or node_id not in node_ids:
            raise ValueError(f"Save data has invalid available node: {node_id}")


def _validate_relic_ids(relic_ids: list):
    if not isinstance(relic_ids, list):
        raise ValueError("Save data has invalid relics")
    for relic_id in relic_ids:
        if relic_id not in RELICS_DB:
            raise ValueError(f"Save data has unknown relic: {relic_id}")


def _validate_potion_ids(potion_ids: list):
    if not isinstance(potion_ids, list):
        raise ValueError("Save data has invalid potions")
    for potion_id in potion_ids:
        if potion_id not in POTIONS_DB:
            raise ValueError(f"Save data has unknown potion: {potion_id}")


def _validate_reward_state(session):
    if not isinstance(session.reward_choices, list) or any(not isinstance(card_id, str) for card_id in session.reward_choices):
        raise ValueError("Save data has invalid reward choices")
    if session.reward_relic is not None and session.reward_relic not in RELICS_DB:
        raise ValueError(f"Save data has unknown reward relic: {session.reward_relic}")
    if not isinstance(session.reward_card_resolved, bool):
        raise ValueError("Save data has invalid reward card state")
    if session.current_event is not None and session.current_event not in EVENTS_DB:
        raise ValueError(f"Save data has unknown event: {session.current_event}")


def _validate_shop_state(session):
    if not isinstance(session.shop_remove_used, bool):
        raise ValueError("Save data has invalid shop remove state")
    if not isinstance(session.shop_cards, list):
        raise ValueError("Save data has invalid shop cards")
    for offer in session.shop_cards:
        if not isinstance(offer, dict):
            raise ValueError("Save data has invalid shop card offer")
        if not isinstance(offer.get("card_id"), str) or not offer["card_id"]:
            raise ValueError("Save data has invalid shop card id")
        if not _is_positive_int(offer.get("price")):
            raise ValueError("Save data has invalid shop card price")

    if not isinstance(session.shop_potions, list):
        raise ValueError("Save data has invalid shop potions")
    for offer in session.shop_potions:
        if not isinstance(offer, dict):
            raise ValueError("Save data has invalid shop potion offer")
        if offer.get("potion_id") not in POTIONS_DB:
            raise ValueError(f"Save data has unknown shop potion: {offer.get('potion_id')}")
        if not _is_positive_int(offer.get("price")):
            raise ValueError("Save data has invalid shop potion price")


def _is_positive_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def load_enemy_db(filepath="data/enemies.json"):
    global ENEMY_TABLE
    if not os.path.exists(filepath):
        print(f"Warning: Enemy DB not found at {filepath}")
        data = deepcopy(DEFAULT_ENEMY_TABLE)
    else:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
    validate_enemy_db(data)
    ENEMY_TABLE = data
    return data

load_enemy_db()

def _make_enemy(tier: str, ascension: int = 0) -> dict:
    if tier not in ENEMY_TABLE or not ENEMY_TABLE[tier]:
        return {"name": "Placeholder", "hp": 10, "attack": 0, "actions": [{"type": "attack", "amount": 1}], "phases": [], "passives": []}

    enemy_data = random.choice(ENEMY_TABLE[tier])
    name = enemy_data[0]
    hp = scale_enemy_hp(enemy_data[1], ascension, tier)
    actions = enemy_data[2]
    extra = enemy_data[3:]

    first_attack = next((action["amount"] for action in actions if action["type"] == "attack"), 0)
    phases = extra[0] if extra and extra[0] else []
    passives = extra[1] if len(extra) > 1 else []
    return {"name": name, "hp": hp, "attack": first_attack, "actions": actions, "phases": phases, "passives": passives}

def _make_enemies(node_type: str, floor: int, ascension: int = 0) -> list:
    if node_type == "Elite":
        return [_make_enemy("elite", ascension)]
    elif node_type == "Boss":
        return [_make_enemy("boss", ascension)]
    elif node_type == "Enemy":
        tier = "easy" if floor <= 3 else "normal"
        count = 1 if floor <= 2 else random.randint(1, 2)
        return [_make_enemy(tier, ascension) for _ in range(count)]
    return []

def generate_map(floors: int = 15, width: int = 3, ascension: int = 0) -> list:
    """Generate a branching run map. Returns list of floor rows, each a list of MapNode."""
    nodes = []
    node_id = 1
    prev_row_ids = []

    for floor in range(1, floors + 1):
        if floor == floors:
            node_type = "Boss"
            count = 1
        elif floor == floors // 2:
            node_type = "Rest"
            count = 1
        elif floor in (floors // 4, floors * 3 // 4):
            node_type = "Shop"
            count = 1
        elif floor >= floors * 2 // 3:
            types = ["Enemy", "Elite", "Elite", "Event"]
            node_type = None
            count = random.randint(1, min(width, 2))
        else:
            types = ["Enemy", "Enemy", "Rest", "Event"] if floor % 5 == 0 else ["Enemy", "Enemy", "Event"]
            node_type = None
            count = random.randint(1, width)

        row = []
        for _ in range(count):
            nt = node_type or random.choice(types)
            enemies = _make_enemies(nt, floor, ascension)
            node = MapNode(node_id, nt, enemies, floor=floor)
            nodes.append(node)
            row.append(node)
            node_id += 1

        # Wire connections: each node in prev row connects to 1-2 nodes in this row
        if prev_row_ids and row:
            row_ids = [n.id for n in row]
            for prev_id in prev_row_ids:
                prev_node = next(n for n in nodes if n.id == prev_id)
                # Connect to random 1-2 nodes in current row
                picks = random.sample(row_ids, min(random.randint(1, 2), len(row_ids)))
                prev_node.connections = sorted(set(prev_node.connections + picks))

        prev_row_ids = [n.id for n in row]

    validate_map_nodes(nodes)
    return nodes

class MapNode:
    def __init__(self, node_id: int, node_type: str, enemies_data: list, floor: int = 0):
        self.id = node_id
        self.type = node_type
        self.enemies_data = enemies_data
        self.floor = floor
        self.completed = False
        self.connections: list = []  # node IDs reachable from here

class Session:
    def __init__(self, player: Player = None, character_id: str = None, ascension: int = 0):
        self.player = player
        if player and not character_id:
            character_id = "ironclad"
        self.character_id = character_id
        self.ascension = clamp_ascension(ascension)
        self.run_won = False
        char = get_character(character_id) if character_id else None
        self.relics = list(char["starter_relics"]) if char else []
        self.master_deck = list(char["starter_deck"]) if char else []
        self.card_pool = list(char["card_pool"]) if char else []
        self.phase = "CHARACTER_SELECT" if not player else "MAP"
        self.current_node_id = None
        self.reward_choices = []
        self.reward_relic = None
        self.reward_card_resolved = False
        self.floor = 0
        self.map_nodes = generate_map(ascension=self.ascension) if player else []
        self.available_node_ids = [n.id for n in self.map_nodes if n.floor == 1]
        self.gold = starting_gold(self.ascension)
        self.potions = []
        self.max_potion_slots = MAX_POTION_SLOTS
        self.shop_cards = []
        self.shop_potions = []
        self.shop_remove_used = False
        self.current_event = None
        self.combat_state = None

    def choose_node(self, node_id: int):
        if node_id not in self.available_node_ids:
            return None
        node = next((n for n in self.map_nodes if n.id == node_id), None)
        if not node or node.completed:
            return None
        self.current_node_id = node_id

        if node.type == "Rest":
            self.phase = "REST"
            return node
        elif node.type == "Shop":
            self._open_shop()
            self.phase = "SHOP"
            return node
        elif node.type == "Event":
            self.current_event = random.choice(list(EVENTS_DB))
            self.phase = "EVENT"
            return node
        else:
            self.phase = "COMBAT"
            return node

    def leave_shop(self):
        if self.phase != "SHOP":
            return False
        node = next((n for n in self.map_nodes if n.id == self.current_node_id), None)
        if node:
            node.completed = True
            self._advance_floor(node)
        self.phase = "MAP"
        self.current_node_id = None
        self.shop_cards = []
        self.shop_potions = []
        self.shop_remove_used = False
        return True

    def _open_shop(self):
        choices = sample_cards(self.card_pool, SHOP_CARD_COUNT)
        self.shop_cards = [
            {
                "card_id": card_id,
                "price": SHOP_CARD_PRICES.get(card_rarity(card_id), SHOP_CARD_PRICE),
            }
            for card_id in choices
        ]
        potion_choices = random.sample(list(POTIONS_DB), min(SHOP_POTION_COUNT, len(POTIONS_DB)))
        self.shop_potions = [
            {"potion_id": potion_id, "price": SHOP_POTION_PRICE}
            for potion_id in potion_choices
        ]
        self.shop_remove_used = False

    def complete_event(self, choice_id: str):
        if self.phase != "EVENT" or not apply_event_choice(self, self.current_event, choice_id):
            return False
        self._complete_current_node()
        self.current_event = None
        self.phase = "GAME_OVER" if self.player.is_dead() else "MAP"
        return True

    def complete_rest(self, action: str, card_index: int = None, can_upgrade=None):
        if self.phase != "REST":
            return False
        if action == "heal":
            self.player.heal(int(self.player.max_hp * rest_heal_fraction(self.ascension)))
        elif action == "upgrade":
            if not self.upgrade_card(card_index, can_upgrade):
                return False
        else:
            return False

        self._complete_current_node()
        self.phase = "MAP"
        return True

    def upgrade_card(self, card_index: int, can_upgrade=None):
        if not isinstance(card_index, int) or not 0 <= card_index < len(self.master_deck):
            return False
        card_id = self.master_deck[card_index]
        if card_id.endswith("+") or (can_upgrade and not can_upgrade(card_id)):
            return False
        self.master_deck[card_index] = f"{card_id}+"
        return True

    def remove_card(self, card_index: int):
        if self.phase != "SHOP" or self.shop_remove_used or self.gold < SHOP_REMOVE_PRICE:
            return False
        if not isinstance(card_index, int) or not 0 <= card_index < len(self.master_deck):
            return False
        if len(self.master_deck) <= 1:
            return False
        self.master_deck.pop(card_index)
        self.gold -= SHOP_REMOVE_PRICE
        self.shop_remove_used = True
        return True

    def _complete_current_node(self):
        node = next((n for n in self.map_nodes if n.id == self.current_node_id), None)
        if node:
            node.completed = True
            self._advance_floor(node)
        self.current_node_id = None

    def _advance_floor(self, node: MapNode):
        self.floor = node.floor
        next_ids = node.connections
        if next_ids:
            self.available_node_ids = next_ids
        else:
            # No more connections: run complete
            self.available_node_ids = []

    def end_combat(self, victory: bool):
        if not victory:
            self.phase = "GAME_OVER"
            return

        node = next((n for n in self.map_nodes if n.id == self.current_node_id), None)
        if node:
            node.completed = True
            self._advance_floor(node)

        for r_id in self.relics:
            trigger_relic_on_combat_end(r_id, self)
        self.player.reset_combat_state()

        # Check win: boss killed
        if node and node.type == "Boss":
            self.run_won = True
            self.phase = "GAME_OVER"
            return

        self.phase = "REWARD"
        self.reward_choices = sample_cards(self.card_pool, 3)
        self.reward_card_resolved = False
        self.reward_relic = self._roll_relic_reward() if node and node.type == "Elite" else None
        self._maybe_add_potion()
        # Gold reward
        gold_gain = random.randint(10, 25) if node and node.type == "Enemy" else random.randint(25, 45)
        self.gold += gold_gain

    def choose_reward(self, card_id: str):
        if self.phase != "REWARD" or self.reward_card_resolved:
            return False
        if card_id is not None and card_id not in self.reward_choices:
            return False
        if card_id and card_id in self.reward_choices:
            self.master_deck.append(card_id)
        self.reward_choices = []
        self.reward_card_resolved = True
        self._finish_reward_if_complete()
        return True

    def claim_relic_reward(self):
        if self.phase != "REWARD" or not self.reward_relic:
            return False
        if self.reward_relic not in self.relics:
            self.relics.append(self.reward_relic)
        self.reward_relic = None
        self._finish_reward_if_complete()
        return True

    def _finish_reward_if_complete(self):
        if not self.reward_card_resolved or self.reward_relic:
            return
        self.phase = "MAP"
        self.reward_card_resolved = False
        self.current_node_id = None

    def _roll_relic_reward(self):
        return roll_relic_reward(self.relics)

    def _maybe_add_potion(self):
        if len(self.potions) >= self.max_potion_slots or random.random() >= POTION_DROP_CHANCE:
            return None
        potion_id = random.choice(list(POTIONS_DB))
        self.potions.append(potion_id)
        return potion_id

    def use_potion(self, potion_index: int, game, target_index: int = 0):
        if self.phase != "COMBAT" or not isinstance(potion_index, int) or not isinstance(target_index, int):
            return False
        if not 0 <= potion_index < len(self.potions):
            return False
        if not use_potion(self.potions[potion_index], game, target_index):
            return False
        self.potions.pop(potion_index)
        return True

    def buy_potion(self, potion_id: str):
        if self.phase != "SHOP" or len(self.potions) >= self.max_potion_slots:
            return False
        offer = next((item for item in self.shop_potions if item["potion_id"] == potion_id), None)
        if not offer or self.gold < offer["price"]:
            return False
        self.gold -= offer["price"]
        self.potions.append(potion_id)
        self.shop_potions.remove(offer)
        return True

    def buy_card(self, card_id: str):
        if self.phase != "SHOP":
            return False
        offer = next((item for item in self.shop_cards if item["card_id"] == card_id), None)
        if not offer or self.gold < offer["price"]:
            return False
        self.gold -= offer["price"]
        self.master_deck.append(card_id)
        self.shop_cards.remove(offer)
        return True

    def compute_score(self) -> int:
        score = self.floor * 10 + self.ascension * 30 + self.gold // 5
        if self.run_won:
            score += 250
        return score

    def run_summary(self) -> dict:
        return {
            "character": self.character_id,
            "ascension": self.ascension,
            "floor": self.floor,
            "won": self.run_won,
            "gold": self.gold,
            "score": self.compute_score(),
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }

    def to_dict(self):
        return {
            "save_version": SAVE_VERSION,
            "player": self.player.to_dict() if self.player else None,
            "character_id": self.character_id,
            "ascension": self.ascension,
            "master_deck": self.master_deck,
            "relics": [RELICS_DB[r_id] for r_id in self.relics if r_id in RELICS_DB],
            "phase": self.phase,
            "current_node_id": self.current_node_id,
            "current_event": event_to_dict(self.current_event),
            "reward_choices": self.reward_choices,
            "reward_relic": RELICS_DB.get(self.reward_relic),
            "reward_card_resolved": self.reward_card_resolved,
            "available_node_ids": self.available_node_ids,
            "floor": self.floor,
            "gold": self.gold,
            "potions": [POTIONS_DB[potion_id] for potion_id in self.potions if potion_id in POTIONS_DB],
            "max_potion_slots": self.max_potion_slots,
            "shop_cards": self.shop_cards,
            "shop_potions": [
                {
                    "potion": POTIONS_DB[offer["potion_id"]],
                    "price": offer["price"],
                }
                for offer in self.shop_potions
                if offer["potion_id"] in POTIONS_DB
            ],
            "shop_remove_price": SHOP_REMOVE_PRICE,
            "shop_remove_used": self.shop_remove_used,
            "map_nodes": [
                {
                    "id": n.id,
                    "type": n.type,
                    "floor": n.floor,
                    "enemies_data": n.enemies_data,
                    "completed": n.completed,
                    "connections": n.connections,
                } for n in self.map_nodes
            ]
        }

    @staticmethod
    def backup_filepath(filepath: str):
        return f"{filepath}{SAVE_BACKUP_SUFFIX}"

    @staticmethod
    def temp_filepath(filepath: str):
        return f"{filepath}{SAVE_TEMP_SUFFIX}"

    @classmethod
    def delete_save_files(cls, filepath: str):
        for active_path in (filepath, cls.backup_filepath(filepath), cls.temp_filepath(filepath)):
            if os.path.exists(active_path):
                os.remove(active_path)

    @classmethod
    def _isolate_invalid_save(cls, filepath: str):
        if not os.path.exists(filepath):
            return None
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        isolated_path = f"{filepath}.invalid-{timestamp}"
        suffix = 1
        while os.path.exists(isolated_path):
            isolated_path = f"{filepath}.invalid-{timestamp}-{suffix}"
            suffix += 1
        os.replace(filepath, isolated_path)
        return isolated_path

    @classmethod
    def _write_json_atomically(cls, filepath: str, data: dict):
        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
        temp_path = cls.temp_filepath(filepath)
        try:
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_path, filepath)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    @classmethod
    def _read_save_data(cls, filepath: str):
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("Save data must be an object")
        if data.get("save_version") != SAVE_VERSION:
            raise ValueError("Unsupported save version")
        if not isinstance(data.get("player"), dict):
            raise ValueError("Save data is missing player state")
        return data

    def save_to_file(self, filepath: str, game=None):
        validate_saved_session(self)
        data = self.to_dict()
        data["combat_state"] = game.to_save_dict() if self.phase == "COMBAT" and game else None
        if os.path.exists(filepath):
            try:
                previous_data = self._read_save_data(filepath)
            except (OSError, json.JSONDecodeError, TypeError, ValueError):
                self._isolate_invalid_save(filepath)
            else:
                self._write_json_atomically(self.backup_filepath(filepath), previous_data)
        self._write_json_atomically(filepath, data)

    @classmethod
    def load_from_file(cls, filepath: str):
        for source_path in (filepath, cls.backup_filepath(filepath)):
            if not os.path.exists(source_path):
                continue
            try:
                data = cls._read_save_data(source_path)
                session = cls._from_save_data(data)
            except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
                cls._isolate_invalid_save(source_path)
                continue
            if source_path != filepath:
                cls._write_json_atomically(filepath, data)
            return session
        return None

    @classmethod
    def _from_save_data(cls, data: dict):
        p_data = data["player"]
        player = Player(p_data["name"], p_data["max_hp"], p_data["max_energy"])
        player.hp = p_data["hp"]
        player.block = p_data.get("block", 0)
        player.buffs = p_data.get("buffs", {})
        player.energy = p_data.get("energy", player.max_energy)
        player.orbs = p_data.get("orbs", [])
        player.max_orb_slots = p_data.get("max_orb_slots", 3)
        char_id = data.get("character_id", "ironclad")
        session = cls(player, character_id=char_id, ascension=data.get("ascension", 0))
        session.master_deck = data.get("master_deck", session.master_deck)
        session.relics = [
            relic["id"] if isinstance(relic, dict) else relic
            for relic in data.get("relics", session.relics)
        ]
        session.phase = data.get("phase", "MAP")
        session.current_node_id = data.get("current_node_id")
        saved_event = data.get("current_event")
        session.current_event = saved_event.get("id") if isinstance(saved_event, dict) else saved_event
        session.reward_choices = data.get("reward_choices", [])
        saved_reward_relic = data.get("reward_relic")
        session.reward_relic = saved_reward_relic.get("id") if isinstance(saved_reward_relic, dict) else saved_reward_relic
        session.reward_card_resolved = data.get("reward_card_resolved", False)
        session.available_node_ids = data.get("available_node_ids", session.available_node_ids)
        session.floor = data.get("floor", 0)
        session.gold = data.get("gold", 99)
        session.max_potion_slots = data.get("max_potion_slots", MAX_POTION_SLOTS)
        session.potions = [
            potion["id"] if isinstance(potion, dict) else potion
            for potion in data.get("potions", [])
        ]
        session.shop_cards = data.get("shop_cards", [])
        session.shop_potions = [
            {
                "potion_id": offer["potion"]["id"] if isinstance(offer.get("potion"), dict) else offer.get("potion_id"),
                "price": offer["price"],
            }
            for offer in data.get("shop_potions", [])
        ]
        session.shop_remove_used = data.get("shop_remove_used", False)
        session.combat_state = data.get("combat_state")
        saved_nodes = data.get("map_nodes", [])
        if saved_nodes:
            session.map_nodes = []
            for n_data in saved_nodes:
                node = MapNode(n_data["id"], n_data["type"], n_data.get("enemies_data", []), floor=n_data.get("floor", 0))
                node.completed = n_data.get("completed", False)
                node.connections = n_data.get("connections", [])
                session.map_nodes.append(node)
        validate_saved_session(session)
        return session
