# Content Schema

This project keeps game content in JSON files under `data/`. Validation runs at load time for cards, characters, enemies, events, potions, and relics. Invalid content should fail fast during tests instead of appearing during a run.

## Shared Rules

- IDs are lowercase snake_case strings unless the file uses array-style enemy entries.
- String fields must be non-empty.
- Numeric combat values are integers unless noted otherwise.
- Rarity values are `common`, `uncommon`, or `rare`.
- Adding a new effect, event action, potion, relic, enemy action, or passive usually requires both data and Python implementation.

## `data/cards.json`

Top-level type: array of card objects.

Required fields:

| Field | Type | Notes |
|-------|------|-------|
| `id` | string | Unique base card ID. Upgraded cards are generated as `id+`. |
| `name` | string | Display name. |
| `cost` | integer | Energy cost. |
| `type` | string | One of `Attack`, `Skill`, `Power`. |
| `effects` | array | List of effect objects. |

Optional fields:

| Field | Type | Notes |
|-------|------|-------|
| `rarity` | string | Defaults to `common`. |
| `exhaust` | boolean | Defaults to `false`. |
| `upgrade` | object | May override `cost` and/or `effects`. |

Supported effect types:

`apply_buff`, `block`, `change_stance`, `channel_orb`, `damage`, `draw`, `evoke_orb`, `gain_energy`, `heal`, `poison`, `remove_buff`.

Example:

```json
{
  "id": "iron_wave",
  "name": "Iron Wave",
  "cost": 1,
  "type": "Attack",
  "rarity": "common",
  "effects": [
    {"type": "damage", "amount": 5},
    {"type": "block", "amount": 5}
  ],
  "upgrade": {
    "effects": [
      {"type": "damage", "amount": 7},
      {"type": "block", "amount": 7}
    ]
  }
}
```

## `data/characters.json`

Top-level type: object keyed by character ID. The `ironclad` key must exist as the default fallback.

Required fields per character:

| Field | Type | Notes |
|-------|------|-------|
| `name` | string | Display name. |
| `description` | string | Character select description. |
| `max_hp` | integer | Starting maximum HP. |
| `max_energy` | integer | Starting energy per turn. |
| `starter_relics` | array | Relic IDs. Can be empty. |
| `starter_deck` | array | Card IDs. Must not be empty. |
| `card_pool` | array | Reward/shop card IDs. Must not be empty. |

Optional fields:

| Field | Type | Notes |
|-------|------|-------|
| `color` | string | Console color escape used by the CLI prototype. |

## `data/enemies.json`

Top-level type: object keyed by tier. Required tiers are `easy`, `normal`, `elite`, and `boss`.

Enemy entries currently use compact array format:

```json
["Name", hp, actions, phases, passives]
```

Required positions:

| Index | Type | Notes |
|-------|------|-------|
| `0` | string | Enemy display name. |
| `1` | integer | Maximum HP, must be positive. |
| `2` | array | At least one action. |

Optional positions:

| Index | Type | Notes |
|-------|------|-------|
| `3` | array | Phase definitions. Use `[]` when omitted but passives are present. |
| `4` | array | Passive names. Supported: `Asleep`, `Enrage`. |

Supported action types:

| Type | Required Fields |
|------|-----------------|
| `attack` | `amount` positive integer |
| `block` | `amount` positive integer |
| `strength` | `amount` positive integer |
| `sleep` | none |

Phase fields:

| Field | Type | Notes |
|-------|------|-------|
| `threshold` | number | Required. HP fraction where phase triggers, `0 < threshold <= 1`. Multiple phases must be descending. |
| `name` | string | Optional display label. |
| `actions` | array | Optional replacement action list. |
| `block` | integer | Optional positive block gain on transition. |
| `strength` | integer | Optional positive strength gain on transition. |

Example:

```json
[
  "The Guardian",
  240,
  [{"type": "attack", "amount": 18}, {"type": "block", "amount": 15}],
  [
    {
      "threshold": 0.5,
      "name": "Defensive Mode",
      "block": 15,
      "actions": [{"type": "block", "amount": 20}, {"type": "attack", "amount": 24}]
    }
  ]
]
```

## Generated Map Nodes

Maps are generated in Python rather than stored in JSON. Validation expects a non-empty list of `MapNode` objects.

Node rules:

| Field | Type | Notes |
|-------|------|-------|
| `id` | positive integer | Must be unique. |
| `type` | string | One of `Enemy`, `Elite`, `Boss`, `Event`, `Rest`, `Shop`. |
| `floor` | positive integer | Connections must point to later floors. |
| `enemies_data` | array | Required and non-empty for combat nodes; empty for non-combat nodes. |
| `completed` | boolean | Completion state. |
| `connections` | array | Target node IDs that must exist on later floors. |

Combat node enemy objects are the expanded runtime form:

```json
{
  "name": "Jaw Worm",
  "hp": 42,
  "attack": 9,
  "actions": [{"type": "attack", "amount": 9}],
  "phases": [],
  "passives": []
}
```

## `data/events.json`

Top-level type: object keyed by event ID.

Required event fields:

| Field | Type |
|-------|------|
| `id` | string matching object key |
| `name` | string |
| `description` | string |
| `choices` | non-empty array |

Required choice fields:

| Field | Type |
|-------|------|
| `id` | string unique within event |
| `label` | string |
| `description` | string |
| `action` | object |

Supported event action types:

| Type | Required Fields |
|------|-----------------|
| `become_vampire` | none |
| `damage_for_relic` | `damage` integer |
| `gain_potion` | `fallback_gold` integer |
| `gold_for_hp` | `hp` integer, `gold` integer |
| `heal_percent` | `amount` integer |
| `heal_percent_cost_gold` | `amount` integer, `gold` integer |
| `leave` | none |
| `remove_random_basic_cost_gold` | `gold` integer |

## `data/potions.json`

Top-level type: object keyed by potion ID.

Required fields:

| Field | Type |
|-------|------|
| `id` | string matching object key |
| `name` | string |
| `description` | string |
| `icon` | string |

Potion IDs must be implemented in `engine/potions.py`.

## `data/relics.json`

Top-level type: object keyed by relic ID.

Required fields:

| Field | Type | Notes |
|-------|------|-------|
| `id` | string | Must match object key. |
| `name` | string | Display name. |
| `description` | string | Tooltip text. |
| `icon` | string | Short UI label. |
| `rewardable` | boolean | Whether normal reward rolls can offer it. |

Optional fields:

| Field | Type | Notes |
|-------|------|-------|
| `rarity` | string | Defaults to `common`. |

Relic IDs must be implemented in `engine/relics.py`.
