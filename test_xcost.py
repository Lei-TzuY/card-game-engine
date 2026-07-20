import unittest

from engine.database import CardDatabase
from engine.entities import Enemy, Player
from engine.game import Game
from engine.potions import use_potion
from engine.relics import trigger_relic_on_combat_start


class XCostCardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = CardDatabase()
        cls.db.load_from_file("data/cards.json")

    def _game(self, energy=3, enemies=None):
        player = Player("Hero", 80, energy)
        enemies = enemies or [Enemy("A", 40), Enemy("B", 40)]
        game = Game(player, enemies, self.db)
        game.setup_deck(["strike"] * 5)
        return game, player

    def test_whirlwind_hits_all_enemies_once_per_energy(self):
        game, player = self._game(energy=3)
        game.hand.cards = [self.db.get_card("whirlwind")]
        self.assertTrue(game.play_card(0, 0))
        self.assertEqual(game.enemies[0].hp, 40 - 15)  # 5 dmg x3
        self.assertEqual(game.enemies[1].hp, 40 - 15)
        self.assertEqual(player.energy, 0)

    def test_skewer_hits_single_target_per_energy(self):
        game, player = self._game(energy=4)
        game.hand.cards = [self.db.get_card("skewer")]
        self.assertTrue(game.play_card(0, 0))
        self.assertEqual(game.enemies[0].hp, 40 - 28)  # 7 dmg x4
        self.assertEqual(game.enemies[1].hp, 40)

    def test_x_card_with_no_energy_does_nothing_but_is_played(self):
        game, player = self._game(energy=0)
        game.hand.cards = [self.db.get_card("whirlwind")]
        self.assertTrue(game.play_card(0, 0))
        self.assertEqual(game.enemies[0].hp, 40)
        self.assertEqual(len(game.hand), 0)

    def test_x_cost_scales_with_strength(self):
        game, player = self._game(energy=2)
        player.apply_buff("strength", 3)  # each of the 2 hits: 5+3 = 8
        game.hand.cards = [self.db.get_card("whirlwind")]
        game.play_card(0, 0)
        self.assertEqual(game.enemies[0].hp, 40 - 16)


class XCostValidationTests(unittest.TestCase):
    def test_string_x_cost_is_accepted(self):
        db = CardDatabase()
        db.load_from_data([
            {"id": "x1", "name": "X1", "cost": "X", "type": "Attack",
             "effects": [{"type": "damage", "amount": 5, "per_energy": True}]},
        ])
        self.assertEqual(db.get_card("x1").cost, "X")

    def test_non_x_string_cost_is_rejected(self):
        db = CardDatabase()
        with self.assertRaises(ValueError):
            db.load_from_data([
                {"id": "bad", "name": "Bad", "cost": "Y", "type": "Attack",
                 "effects": [{"type": "damage", "amount": 5}]},
            ])


class NewPotionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = CardDatabase()
        cls.db.load_from_file("data/cards.json")

    def _game(self):
        return Game(Player("Hero", 80), [Enemy("A", 30), Enemy("B", 30)], self.db)

    def test_explosive_potion_hits_all_enemies(self):
        game = self._game()
        self.assertTrue(use_potion("explosive_potion", game))
        self.assertEqual(game.enemies[0].hp, 20)
        self.assertEqual(game.enemies[1].hp, 20)

    def test_ancient_potion_grants_artifact(self):
        game = self._game()
        self.assertTrue(use_potion("ancient_potion", game))
        self.assertEqual(game.player.get_buff("artifact"), 1)


class RedMaskRelicTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = CardDatabase()
        cls.db.load_from_file("data/cards.json")

    def test_red_mask_weakens_all_enemies(self):
        game = Game(Player("Hero", 80), [Enemy("A", 30), Enemy("B", 30)], self.db, relics=["red_mask"])
        trigger_relic_on_combat_start("red_mask", game)
        self.assertEqual(game.enemies[0].get_buff("weak"), 1)
        self.assertEqual(game.enemies[1].get_buff("weak"), 1)


if __name__ == "__main__":
    unittest.main()
