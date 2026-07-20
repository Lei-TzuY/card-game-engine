import unittest
from collections import Counter
from types import SimpleNamespace

from engine.database import CardDatabase, card_rarity
from engine.entities import Enemy, Player
from engine.game import Game
from engine.potions import use_potion
from engine.rarity import weighted_sample
from engine.relics import (
    relic_rarity,
    roll_relic_reward,
    trigger_relic_on_card_play,
    trigger_relic_on_combat_start,
    trigger_relic_on_combat_end,
    trigger_relic_on_turn_end,
)
from engine.session import SHOP_CARD_PRICES, Session, sample_cards


class NewRelicTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = CardDatabase()
        cls.db.load_from_file("data/cards.json")

    def _combat(self, relics):
        player = Player("Hero", 80)
        game = Game(player, [Enemy("Slime", 40), Enemy("Goblin", 30)], self.db, relics=relics)
        game.setup_deck(["strike"] * 10)
        return game

    def test_bag_of_marbles_makes_all_enemies_vulnerable(self):
        game = self._combat(["bag_of_marbles"])
        game.start_combat()
        for enemy in game.enemies:
            self.assertEqual(enemy.get_buff("vulnerable"), 1)

    def test_bag_of_preparation_draws_two_extra_cards(self):
        game = self._combat(["bag_of_preparation"])
        game.start_combat()
        self.assertEqual(len(game.hand), game.cards_drawn_per_turn + 2)

    def test_kunai_grants_dexterity_every_third_attack(self):
        game = self._combat(["kunai"])
        attack = self.db.get_card("strike")
        for _ in range(2):
            trigger_relic_on_card_play("kunai", game, attack)
        self.assertEqual(game.player.get_buff("dexterity"), 0)
        trigger_relic_on_card_play("kunai", game, attack)
        self.assertEqual(game.player.get_buff("dexterity"), 1)

    def test_shuriken_grants_strength_every_third_attack(self):
        game = self._combat(["shuriken"])
        attack = self.db.get_card("strike")
        for _ in range(3):
            trigger_relic_on_card_play("shuriken", game, attack)
        self.assertEqual(game.player.get_buff("strength"), 1)

    def test_letter_opener_damages_all_enemies_every_third_skill(self):
        game = self._combat(["letter_opener"])
        skill = self.db.get_card("defend")
        for _ in range(3):
            trigger_relic_on_card_play("letter_opener", game, skill)
        self.assertEqual(game.enemies[0].hp, 35)
        self.assertEqual(game.enemies[1].hp, 25)

    def test_letter_opener_ignores_attacks(self):
        game = self._combat(["letter_opener"])
        attack = self.db.get_card("strike")
        for _ in range(3):
            trigger_relic_on_card_play("letter_opener", game, attack)
        self.assertEqual(game.enemies[0].hp, 40)

    def test_meat_on_the_bone_heals_only_when_low(self):
        low = Player("Hero", 80)
        low.hp = 40
        trigger_relic_on_combat_end("meat_on_the_bone", SimpleNamespace(player=low))
        self.assertEqual(low.hp, 52)

        high = Player("Hero", 80)
        high.hp = 60
        trigger_relic_on_combat_end("meat_on_the_bone", SimpleNamespace(player=high))
        self.assertEqual(high.hp, 60)

    def test_lantern_grants_starting_energy(self):
        game = self._combat(["lantern"])

        trigger_relic_on_combat_start("lantern", game)

        self.assertEqual(game.player.energy, 4)

    def test_thread_and_needle_grants_starting_block(self):
        game = self._combat(["thread_and_needle"])

        trigger_relic_on_combat_start("thread_and_needle", game)

        self.assertEqual(game.player.block, 4)

    def test_mercury_hourglass_damages_all_enemies_at_turn_end(self):
        game = self._combat(["mercury_hourglass"])

        trigger_relic_on_turn_end("mercury_hourglass", game)

        self.assertEqual(game.enemies[0].hp, 37)
        self.assertEqual(game.enemies[1].hp, 27)


class NewPotionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = CardDatabase()
        cls.db.load_from_file("data/cards.json")

    def _game(self):
        player = Player("Hero", 80)
        game = Game(player, [Enemy("Slime", 40), Enemy("Goblin", 30)], self.db)
        game.setup_deck(["strike"] * 10)
        return game

    def test_swift_potion_draws_three(self):
        game = self._game()
        self.assertTrue(use_potion("swift_potion", game))
        self.assertEqual(len(game.hand), 3)

    def test_weak_potion_targets_selected_enemy(self):
        game = self._game()
        self.assertTrue(use_potion("weak_potion", game, target_index=1))
        self.assertEqual(game.enemies[1].get_buff("weak"), 3)
        self.assertEqual(game.enemies[0].get_buff("weak"), 0)

    def test_fear_potion_applies_vulnerable(self):
        game = self._game()
        self.assertTrue(use_potion("fear_potion", game, target_index=0))
        self.assertEqual(game.enemies[0].get_buff("vulnerable"), 3)

    def test_blood_potion_heals_quarter_max_hp(self):
        game = self._game()
        game.player.hp = 40
        self.assertTrue(use_potion("blood_potion", game))
        self.assertEqual(game.player.hp, 60)


class RaritySystemTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = CardDatabase()
        cls.db.load_from_file("data/cards.json")

    def test_cards_carry_rarity_in_serialized_form(self):
        self.assertEqual(self.db.get_card("strike").to_dict()["rarity"], "common")
        self.assertEqual(self.db.get_card("apparition").to_dict()["rarity"], "rare")
        # Upgraded copies keep their base rarity.
        self.assertEqual(self.db.get_card("uppercut+").rarity, "rare")

    def test_card_rarity_lookup_strips_upgrade_marker(self):
        self.assertEqual(card_rarity("glacier"), "rare")
        self.assertEqual(card_rarity("glacier+"), "rare")
        self.assertEqual(card_rarity("unknown_card"), "common")

    def test_weighted_sample_returns_distinct_items(self):
        pool = ["a", "b", "c", "d"]
        picks = weighted_sample(pool, lambda item: 1, 3)
        self.assertEqual(len(picks), 3)
        self.assertEqual(len(set(picks)), 3)

    def test_weighted_sample_caps_at_pool_size(self):
        picks = weighted_sample(["a", "b"], lambda item: 1, 5)
        self.assertEqual(sorted(picks), ["a", "b"])

    def test_reward_rolls_favour_common_over_rare(self):
        pool = ["strike", "uppercut", "apparition", "glacier", "inflame", "iron_wave"]
        counts = Counter()
        for _ in range(4000):
            for card_id in sample_cards(pool, 2):
                counts[card_rarity(card_id)] += 1
        self.assertGreater(counts["common"], counts["rare"])

    def test_shop_prices_scale_with_rarity(self):
        session = Session(Player("Hero", 80), character_id="ironclad")
        session._open_shop()
        for offer in session.shop_cards:
            expected = SHOP_CARD_PRICES[card_rarity(offer["card_id"])]
            self.assertEqual(offer["price"], expected)
        self.assertLess(SHOP_CARD_PRICES["common"], SHOP_CARD_PRICES["rare"])

    def test_relic_reward_roll_respects_rarity_and_ownership(self):
        owned = ["vajra"]
        for _ in range(50):
            relic_id = roll_relic_reward(owned)
            self.assertIsNotNone(relic_id)
            self.assertNotIn(relic_id, owned)
            self.assertIn(relic_rarity(relic_id), ("common", "uncommon", "rare"))


if __name__ == "__main__":
    unittest.main()
