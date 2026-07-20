import json
import os
import tempfile
import unittest

from engine.characters import CHARACTERS, DEFAULT_CHARACTERS, load_character_db
from engine.database import CardDatabase
from engine.events import DEFAULT_EVENTS_DB, EVENTS_DB, load_events_db, validate_events_db
from engine.potions import DEFAULT_POTIONS_DB, POTIONS_DB, load_potions_db, validate_potions_db
from engine.relics import DEFAULT_RELICS_DB, RELICS_DB, load_relics_db, validate_relics_db
import engine.session as session_module


class CharacterDataTests(unittest.TestCase):
    def test_character_database_loads_from_json(self):
        self.assertEqual(len(CHARACTERS), 5)
        self.assertIn("sentinel", CHARACTERS)
        self.assertEqual(CHARACTERS["ironclad"]["max_hp"], 80)
        self.assertEqual(CHARACTERS["silent"]["starter_deck"][-1], "neutralize")
        self.assertIn("wreath_of_flame", CHARACTERS["watcher"]["card_pool"])
        self.assertEqual(CHARACTERS["sentinel"]["max_hp"], 84)
        self.assertIn("body_slam", CHARACTERS["sentinel"]["starter_deck"])
        self.assertEqual(CHARACTERS["sentinel"]["starter_relics"], ["bronze_scales"])

    def test_missing_character_database_uses_fallback(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            missing_path = os.path.join(temp_dir, "missing-characters.json")

            characters = load_character_db(missing_path)

        self.assertEqual(characters["ironclad"]["starter_relics"], ["burning_blood"])
        self.assertEqual(characters, DEFAULT_CHARACTERS)
        self.assertIsNot(characters, DEFAULT_CHARACTERS)

    def test_invalid_character_database_is_rejected(self):
        invalid_data = {
            "ironclad": {
                "name": "Ironclad",
                "description": "Missing required fields.",
                "max_hp": 80,
                "max_energy": 3,
                "starter_relics": [],
                "starter_deck": [],
                "card_pool": ["strike"],
            }
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "characters.json")
            with open(path, "w", encoding="utf-8") as character_file:
                json.dump(invalid_data, character_file)

            with self.assertRaises(ValueError):
                load_character_db(path)


class CardDataTests(unittest.TestCase):
    def test_card_database_loads_current_json_without_duplicate_ids(self):
        db = CardDatabase()

        db.load_from_file("data/cards.json")

        self.assertIn("eruption", db.cards)
        self.assertIn("vigilance", db.cards)
        self.assertIn("iron_wave", db.cards)
        self.assertIn("apparition", db.cards)
        self.assertIn("metallicize", db.cards)
        self.assertIn("barricade", db.cards)
        self.assertIn("body_slam", db.cards)
        self.assertIn("whirlwind", db.cards)
        self.assertEqual(len(db.cards), 54)
        self.assertEqual(db.get_card("eruption").effects[1]["type"], "change_stance")

    def test_duplicate_card_id_is_rejected(self):
        db = CardDatabase()

        with self.assertRaises(ValueError):
            db.load_from_data([
                {
                    "id": "strike",
                    "name": "Strike",
                    "cost": 1,
                    "type": "Attack",
                    "effects": [{"type": "damage", "amount": 6}],
                },
                {
                    "id": "strike",
                    "name": "Duplicate Strike",
                    "cost": 1,
                    "type": "Attack",
                    "effects": [{"type": "damage", "amount": 1}],
                },
            ])

    def test_invalid_card_data_is_rejected_without_mutating_existing_cards(self):
        db = CardDatabase()
        db.load_from_data([
            {
                "id": "strike",
                "name": "Strike",
                "cost": 1,
                "type": "Attack",
                "effects": [{"type": "damage", "amount": 6}],
            }
        ])

        with self.assertRaises(ValueError):
            db.load_from_data([
                {
                    "id": "bad_card",
                    "name": "Bad Card",
                    "cost": "free",
                    "type": "Skill",
                    "effects": [],
                }
            ])

        self.assertEqual(set(db.cards), {"strike"})

    def test_invalid_card_rarity_is_rejected(self):
        db = CardDatabase()

        with self.assertRaises(ValueError):
            db.load_from_data([
                {
                    "id": "shiny",
                    "name": "Shiny",
                    "cost": 1,
                    "type": "Skill",
                    "effects": [{"type": "draw", "amount": 1}],
                    "rarity": "legendary",
                }
            ])

    def test_unknown_card_effect_type_is_rejected(self):
        db = CardDatabase()

        with self.assertRaises(ValueError):
            db.load_from_data([
                {
                    "id": "mystery",
                    "name": "Mystery",
                    "cost": 1,
                    "type": "Skill",
                    "effects": [{"type": "unsupported_effect"}],
                }
            ])


class EventDataTests(unittest.TestCase):
    def test_event_database_loads_from_json(self):
        events = load_events_db()

        self.assertEqual(events, EVENTS_DB)
        self.assertIn("healing_spring", events)
        self.assertIn("choices", events["golden_idol"])

    def test_missing_event_database_uses_fallback(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            missing_path = os.path.join(temp_dir, "missing-events.json")

            events = load_events_db(missing_path)

        self.assertEqual(events, DEFAULT_EVENTS_DB)
        self.assertIsNot(events, DEFAULT_EVENTS_DB)

    def test_event_database_validates_current_data(self):
        validate_events_db(EVENTS_DB)
        self.assertIn("healing_spring", EVENTS_DB)
        self.assertIn("choices", EVENTS_DB["golden_idol"])

    def test_unknown_event_action_type_is_rejected(self):
        with self.assertRaises(ValueError):
            validate_events_db({
                "bad_event": {
                    "id": "bad_event",
                    "name": "Bad Event",
                    "description": "Invalid action.",
                    "choices": [
                        {
                            "id": "bad",
                            "label": "Bad",
                            "description": "Do something unsupported.",
                            "action": {"type": "unsupported_action"},
                        }
                    ],
                }
            })


class PotionDataTests(unittest.TestCase):
    def test_potion_database_loads_from_json(self):
        potions = load_potions_db()

        self.assertEqual(potions, POTIONS_DB)
        self.assertIn("fire_potion", potions)

    def test_missing_potion_database_uses_fallback(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            missing_path = os.path.join(temp_dir, "missing-potions.json")

            potions = load_potions_db(missing_path)

        self.assertEqual(potions, DEFAULT_POTIONS_DB)
        self.assertIsNot(potions, DEFAULT_POTIONS_DB)

    def test_potion_database_validates_current_data(self):
        validate_potions_db(POTIONS_DB)
        self.assertIn("fire_potion", POTIONS_DB)

    def test_unimplemented_potion_id_is_rejected(self):
        with self.assertRaises(ValueError):
            validate_potions_db({
                "mystery_potion": {
                    "id": "mystery_potion",
                    "name": "Mystery Potion",
                    "description": "No implementation.",
                    "icon": "M",
                }
            })


class RelicDataTests(unittest.TestCase):
    def test_relic_database_loads_from_json(self):
        relics = load_relics_db()

        self.assertEqual(relics, RELICS_DB)
        self.assertIn("vajra", relics)
        self.assertEqual(relics["pen_nib"]["icon"], "PN")

    def test_missing_relic_database_uses_fallback(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            missing_path = os.path.join(temp_dir, "missing-relics.json")

            relics = load_relics_db(missing_path)

        self.assertEqual(relics, DEFAULT_RELICS_DB)
        self.assertIsNot(relics, DEFAULT_RELICS_DB)

    def test_relic_database_validates_current_data(self):
        validate_relics_db(RELICS_DB)
        self.assertIn("vajra", RELICS_DB)
        self.assertEqual(RELICS_DB["pen_nib"]["icon"], "PN")

    def test_unimplemented_relic_id_is_rejected(self):
        with self.assertRaises(ValueError):
            validate_relics_db({
                "mystery_relic": {
                    "id": "mystery_relic",
                    "name": "Mystery Relic",
                    "description": "No trigger implementation.",
                    "icon": "M",
                    "rewardable": True,
                }
            })


class EnemyDataTests(unittest.TestCase):
    def test_enemy_database_loads_from_json(self):
        enemies = session_module.load_enemy_db()

        self.assertEqual(enemies, session_module.ENEMY_TABLE)
        self.assertIn("easy", enemies)
        self.assertIn("boss", enemies)
        self.assertTrue(enemies["boss"][0][3])

    def test_missing_enemy_database_uses_fallback(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            missing_path = os.path.join(temp_dir, "missing-enemies.json")

            enemies = session_module.load_enemy_db(missing_path)

        self.assertEqual(enemies, session_module.DEFAULT_ENEMY_TABLE)
        self.assertIsNot(enemies, session_module.DEFAULT_ENEMY_TABLE)

    def test_enemy_database_validates_current_data(self):
        session_module.validate_enemy_db(session_module.ENEMY_TABLE)

    def test_unknown_enemy_action_type_is_rejected_without_mutating_table(self):
        previous_table = session_module.ENEMY_TABLE
        invalid_data = {
            "easy": [["Bad", 10, [{"type": "unsupported_action", "amount": 1}]]],
            "normal": [["Normal", 20, [{"type": "attack", "amount": 5}]]],
            "elite": [["Elite", 80, [{"type": "attack", "amount": 12}]]],
            "boss": [["Boss", 160, [{"type": "attack", "amount": 20}]]],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "enemies.json")
            with open(path, "w", encoding="utf-8") as enemy_file:
                json.dump(invalid_data, enemy_file)

            with self.assertRaises(ValueError):
                session_module.load_enemy_db(path)

        self.assertIs(session_module.ENEMY_TABLE, previous_table)

    def test_unknown_enemy_passive_is_rejected(self):
        with self.assertRaises(ValueError):
            session_module.validate_enemy_db({
                "easy": [["Bad", 10, [{"type": "attack", "amount": 1}], [], ["UnknownPassive"]]],
                "normal": [["Normal", 20, [{"type": "attack", "amount": 5}]]],
                "elite": [["Elite", 80, [{"type": "attack", "amount": 12}]]],
                "boss": [["Boss", 160, [{"type": "attack", "amount": 20}]]],
            })


if __name__ == "__main__":
    unittest.main()
