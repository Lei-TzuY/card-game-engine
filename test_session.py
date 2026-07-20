import json
import os
import tempfile
import unittest
from unittest.mock import patch

from engine.entities import Player
from engine.entities import Enemy
from engine.game import Game
from engine.database import CardDatabase
from engine.session import MapNode, SAVE_VERSION, Session, _make_enemies, generate_map, validate_map_nodes


def enemy_data(name="Slime", hp=10, attack=5):
    return {
        "name": name,
        "hp": hp,
        "attack": attack,
        "actions": [{"type": "attack", "amount": attack}],
        "phases": [],
        "passives": [],
    }


def make_session():
    session = Session(Player("Hero", 50))
    rest = MapNode(1, "Rest", [], floor=1)
    shop = MapNode(2, "Shop", [], floor=2)
    enemy = MapNode(3, "Enemy", [enemy_data()], floor=3)
    rest.connections = [shop.id]
    shop.connections = [enemy.id]
    session.map_nodes = [rest, shop, enemy]
    session.available_node_ids = [rest.id]
    return session


class SessionTests(unittest.TestCase):
    def test_rest_and_shop_advance_the_map(self):
        session = make_session()
        session.player.hp = 30

        rest = session.choose_node(1)
        self.assertEqual(rest.type, "Rest")
        self.assertEqual(session.phase, "REST")
        self.assertEqual(session.player.hp, 30)

        self.assertTrue(session.complete_rest("heal"))
        self.assertEqual(session.player.hp, 45)
        self.assertEqual(session.phase, "MAP")
        self.assertEqual(session.current_node_id, None)
        self.assertEqual(session.available_node_ids, [2])

        shop = session.choose_node(2)
        self.assertEqual(shop.type, "Shop")
        self.assertEqual(session.phase, "SHOP")
        self.assertEqual(len(session.shop_cards), 3)

        card_id = session.shop_cards[0]["card_id"]
        card_price = session.shop_cards[0]["price"]
        starting_deck_size = len(session.master_deck)
        session.gold = card_price
        self.assertTrue(session.buy_card(card_id))
        self.assertEqual(session.gold, 0)
        self.assertEqual(len(session.master_deck), starting_deck_size + 1)
        self.assertFalse(session.buy_card(card_id))

        self.assertTrue(session.leave_shop())
        self.assertEqual(session.phase, "MAP")
        self.assertEqual(session.available_node_ids, [3])
        self.assertEqual(session.shop_cards, [])

    def test_shop_rejects_cards_that_are_not_offered(self):
        session = make_session()
        session.choose_node(1)
        session.complete_rest("heal")
        session.choose_node(2)

        self.assertFalse(session.buy_card("not-a-real-offer"))

    def test_combat_victory_clears_temporary_player_state(self):
        session = make_session()
        session.current_node_id = 3
        session.player.hp = 40
        session.player.block = 9
        session.player.apply_buff("strength", 2)

        session.end_combat(True)

        self.assertEqual(session.player.hp, 46)
        self.assertEqual(session.player.block, 0)
        self.assertEqual(session.player.buffs, {})
        self.assertEqual(session.phase, "REWARD")

    def test_shop_state_survives_save_round_trip(self):
        session = make_session()
        session.choose_node(1)
        session.complete_rest("heal")
        session.choose_node(2)

        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "save.json")
            session.save_to_file(path)
            loaded = Session.load_from_file(path)

        self.assertEqual(loaded.phase, "SHOP")
        self.assertEqual(loaded.current_node_id, 2)
        self.assertEqual(loaded.shop_cards, session.shop_cards)
        self.assertEqual(loaded.available_node_ids, [2])

    def test_legacy_save_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "save.json")
            with open(path, "w", encoding="utf-8") as save_file:
                json.dump({"player": {}}, save_file)

            self.assertIsNone(Session.load_from_file(path))

    def test_serialized_save_version_is_current(self):
        self.assertEqual(make_session().to_dict()["save_version"], SAVE_VERSION)

    def test_rest_can_upgrade_one_card(self):
        session = make_session()
        session.choose_node(1)

        self.assertTrue(session.complete_rest("upgrade", 0))

        self.assertEqual(session.master_deck[0], "strike+")
        self.assertEqual(session.phase, "MAP")
        self.assertFalse(session.upgrade_card(0))

    def test_shop_can_remove_only_one_card(self):
        session = make_session()
        session.choose_node(1)
        session.complete_rest("heal")
        session.choose_node(2)
        session.gold = 200
        starting_size = len(session.master_deck)

        self.assertTrue(session.remove_card(0))

        self.assertEqual(len(session.master_deck), starting_size - 1)
        self.assertEqual(session.gold, 125)
        self.assertTrue(session.shop_remove_used)
        self.assertFalse(session.remove_card(0))

    def test_rest_and_shop_remove_state_survive_save_round_trip(self):
        rest_session = make_session()
        rest_session.choose_node(1)

        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "rest-save.json")
            rest_session.save_to_file(path)
            loaded_rest = Session.load_from_file(path)

        self.assertEqual(loaded_rest.phase, "REST")
        self.assertEqual(loaded_rest.current_node_id, 1)

        shop_session = make_session()
        shop_session.choose_node(1)
        shop_session.complete_rest("heal")
        shop_session.choose_node(2)
        shop_session.remove_card(0)

        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "shop-save.json")
            shop_session.save_to_file(path)
            loaded_shop = Session.load_from_file(path)

        self.assertTrue(loaded_shop.shop_remove_used)

    def test_silent_has_poison_cards(self):
        session = Session(Player("Silent", 70), character_id="silent")

        self.assertIn("neutralize", session.master_deck)
        self.assertIn("deadly_poison", session.card_pool)
        self.assertIn("poisoned_stab", session.card_pool)

    def test_defect_has_orb_cards(self):
        session = Session(Player("Defect", 75), character_id="defect")

        self.assertIn("zap", session.master_deck)
        self.assertIn("dualcast", session.master_deck)
        self.assertIn("coolheaded", session.card_pool)
        self.assertIn("ball_lightning", session.card_pool)

    def test_elite_reward_waits_for_card_and_relic_claim(self):
        session = make_session()
        elite = MapNode(4, "Elite", [enemy_data("Elite", 1)], floor=3)
        session.map_nodes = [elite]
        session.current_node_id = elite.id

        with patch("engine.session.roll_relic_reward", return_value="vajra"), \
                patch("engine.session.random.random", return_value=1):
            session.end_combat(True)

        self.assertEqual(session.reward_relic, "vajra")
        self.assertTrue(session.choose_reward(None))
        self.assertEqual(session.phase, "REWARD")
        self.assertTrue(session.claim_relic_reward())
        self.assertEqual(session.phase, "MAP")
        self.assertIn("vajra", session.relics)

    def test_combat_can_drop_a_potion_when_slot_is_available(self):
        session = make_session()
        session.current_node_id = 3

        with patch("engine.session.random.random", return_value=0), \
                patch("engine.session.random.choice", return_value="fire_potion"):
            session.end_combat(True)

        self.assertEqual(session.potions, ["fire_potion"])
        self.assertEqual(session.to_dict()["potions"][0]["name"], "Fire Potion")

    def test_potion_inventory_has_three_slots(self):
        session = make_session()
        session.potions = ["fire_potion", "block_potion", "strength_potion"]

        with patch("engine.session.random.random", return_value=0):
            self.assertIsNone(session._maybe_add_potion())

        self.assertEqual(len(session.potions), 3)
        self.assertEqual(session.to_dict()["max_potion_slots"], 3)

    def test_reward_and_potion_state_survive_save_round_trip(self):
        session = make_session()
        session.phase = "REWARD"
        session.reward_relic = "anchor"
        session.reward_card_resolved = True
        session.potions = ["block_potion"]

        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "reward-save.json")
            session.save_to_file(path)
            loaded = Session.load_from_file(path)

        self.assertEqual(loaded.reward_relic, "anchor")
        self.assertTrue(loaded.reward_card_resolved)
        self.assertEqual(loaded.potions, ["block_potion"])

    def test_healing_spring_event_heals_and_advances_map(self):
        session = make_session()
        event = MapNode(4, "Event", [], floor=1)
        next_node = MapNode(5, "Enemy", [enemy_data()], floor=2)
        event.connections = [next_node.id]
        session.map_nodes = [event, next_node]
        session.available_node_ids = [event.id]
        session.player.hp = 20

        with patch("engine.session.random.choice", return_value="healing_spring"):
            session.choose_node(event.id)

        self.assertEqual(session.phase, "EVENT")
        self.assertTrue(session.complete_event("drink"))
        self.assertEqual(session.player.hp, 30)
        self.assertEqual(session.phase, "MAP")
        self.assertEqual(session.available_node_ids, [next_node.id])

    def test_potion_lab_event_gives_gold_when_inventory_is_full(self):
        session = make_session()
        session.phase = "EVENT"
        session.current_event = "potion_lab"
        session.current_node_id = 1
        session.potions = ["fire_potion", "block_potion", "strength_potion"]
        starting_gold = session.gold

        self.assertTrue(session.complete_event("search"))

        self.assertEqual(session.gold, starting_gold + 30)
        self.assertEqual(len(session.potions), 3)

    def test_shop_can_sell_potions_until_inventory_is_full(self):
        session = make_session()
        session.choose_node(1)
        session.complete_rest("heal")
        session.choose_node(2)
        potion_id = session.shop_potions[0]["potion_id"]
        session.gold = 100

        self.assertTrue(session.buy_potion(potion_id))
        self.assertEqual(session.gold, 60)
        self.assertIn(potion_id, session.potions)

        session.potions = ["fire_potion", "block_potion", "strength_potion"]
        self.assertFalse(session.buy_potion(session.shop_potions[0]["potion_id"]))

    def test_event_and_shop_potions_survive_save_round_trip(self):
        event_session = make_session()
        event_session.phase = "EVENT"
        event_session.current_event = "golden_idol"
        event_session.current_node_id = 1

        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "event-save.json")
            event_session.save_to_file(path)
            loaded_event = Session.load_from_file(path)

        self.assertEqual(loaded_event.current_event, "golden_idol")

        shop_session = make_session()
        shop_session.choose_node(1)
        shop_session.complete_rest("heal")
        shop_session.choose_node(2)

        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "shop-potion-save.json")
            shop_session.save_to_file(path)
            loaded_shop = Session.load_from_file(path)

        self.assertEqual(loaded_shop.shop_potions, shop_session.shop_potions)

    def test_combat_save_round_trip_preserves_temporary_player_state(self):
        session = make_session()
        session.phase = "COMBAT"
        session.current_node_id = 3
        session.player.hp = 37
        session.player.block = 8
        session.player.energy = 1
        session.player.apply_buff("strength", 2)
        session.player.orbs = ["frost"]
        db = CardDatabase()
        db.load_from_file("data/cards.json")
        game = Game(session.player, [Enemy("Slime", 30)], db)
        game.hand.add(db.get_card("defend"))

        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "combat-save.json")
            session.save_to_file(path, game)
            loaded = Session.load_from_file(path)

        self.assertEqual(loaded.phase, "COMBAT")
        self.assertEqual(loaded.player.hp, 37)
        self.assertEqual(loaded.player.block, 8)
        self.assertEqual(loaded.player.energy, 1)
        self.assertEqual(loaded.player.get_buff("strength"), 2)
        self.assertEqual(loaded.player.orbs, ["frost"])
        self.assertEqual(loaded.combat_state["hand"], ["defend"])

    def test_boss_encounter_has_a_phase_transition(self):
        enemies = _make_enemies("Boss", floor=15)

        self.assertEqual(len(enemies), 1)
        self.assertTrue(enemies[0]["phases"])
        self.assertEqual(enemies[0]["phases"][0]["threshold"], 0.5)

    def test_generated_map_passes_structural_validation(self):
        nodes = generate_map(floors=15, width=3)

        validate_map_nodes(nodes)
        self.assertTrue(any(node.type == "Boss" for node in nodes))
        self.assertTrue(all(target > 0 for node in nodes for target in node.connections))

    def test_map_validation_rejects_backward_connections(self):
        late = MapNode(1, "Rest", [], floor=2)
        early = MapNode(
            2,
            "Enemy",
            [enemy_data()],
            floor=1,
        )
        late.connections = [early.id]

        with self.assertRaises(ValueError):
            validate_map_nodes([late, early])

    def test_atomic_save_keeps_previous_valid_backup(self):
        session = make_session()

        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "save.json")
            session.player.hp = 40
            session.save_to_file(path)
            session.player.hp = 25
            session.save_to_file(path)

            with open(Session.backup_filepath(path), encoding="utf-8") as backup_file:
                backup = json.load(backup_file)

            self.assertEqual(backup["player"]["hp"], 40)
            self.assertFalse(os.path.exists(Session.temp_filepath(path)))

    def test_corrupt_primary_save_recovers_backup_and_isolates_bad_file(self):
        session = make_session()

        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "save.json")
            session.player.hp = 40
            session.save_to_file(path)
            session.player.hp = 25
            session.save_to_file(path)
            with open(path, "w", encoding="utf-8") as save_file:
                save_file.write("{bad json")

            loaded = Session.load_from_file(path)

            self.assertEqual(loaded.player.hp, 40)
            self.assertTrue(os.path.exists(path))
            invalid_files = [name for name in os.listdir(temp_dir) if ".invalid-" in name]
            self.assertEqual(len(invalid_files), 1)

    def test_invalid_primary_save_recovers_backup_and_isolates_bad_file(self):
        session = make_session()

        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "save.json")
            session.player.hp = 40
            session.save_to_file(path)
            session.player.hp = 25
            session.save_to_file(path)
            with open(path, encoding="utf-8") as save_file:
                data = json.load(save_file)
            data["potions"] = ["unknown_potion"]
            with open(path, "w", encoding="utf-8") as save_file:
                json.dump(data, save_file)

            loaded = Session.load_from_file(path)

            self.assertEqual(loaded.player.hp, 40)
            invalid_files = [name for name in os.listdir(temp_dir) if ".invalid-" in name]
            self.assertEqual(len(invalid_files), 1)

    def test_invalid_saved_map_without_backup_is_isolated(self):
        session = make_session()

        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "save.json")
            session.save_to_file(path)
            with open(path, encoding="utf-8") as save_file:
                data = json.load(save_file)
            data["map_nodes"][0]["connections"] = [999]
            with open(path, "w", encoding="utf-8") as save_file:
                json.dump(data, save_file)

            self.assertIsNone(Session.load_from_file(path))

            self.assertFalse(os.path.exists(path))
            invalid_files = [name for name in os.listdir(temp_dir) if ".invalid-" in name]
            self.assertEqual(len(invalid_files), 1)

    def test_corrupt_save_without_backup_is_isolated(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "save.json")
            with open(path, "w", encoding="utf-8") as save_file:
                save_file.write("{bad json")

            self.assertIsNone(Session.load_from_file(path))

            self.assertFalse(os.path.exists(path))
            invalid_files = [name for name in os.listdir(temp_dir) if ".invalid-" in name]
            self.assertEqual(len(invalid_files), 1)


if __name__ == "__main__":
    unittest.main()
