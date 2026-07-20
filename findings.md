# Findings

## Session Notes
- Started from user estimate of 91% complete: core loop, save isolation, data-driven character/card/event/potion/relic validation, and server API tests are stable.
- Next high-value targets are enemy/map validation, schema docs, and more balanced event/enemy/relic content.
- Project has no central `engine/content.py` or `engine/models.py`; validation is implemented per content domain (`characters`, `database/cards`, `events`, `potions`, `relics`) and should be extended in that style.
- Enemy content is loaded in `engine/session.py` from `data/enemies.json` into global `ENEMY_TABLE`; current format is `{tier: [[name, hp, actions, phases?, passives?], ...]}`.
- `Enemy` supports action types `attack`, `block`, `strength`, and `sleep`; phases can change actions and grant block/strength at HP thresholds; passives currently implemented are `Asleep` and `Enrage`.
- Map generation is also in `engine/session.py`; nodes have type, floor, enemies_data, completion flag, and forward connections. Existing tests cover flow and boss phase presence but not map structural validity.
- `server.choose_node` currently passes enemy name/hp/attack/actions/phases into `Enemy` but omits generated `passives`, so passive enemies can lose behavior in API combat.
