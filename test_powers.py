import unittest

from engine.database import CardDatabase
from engine.effects import execute_effects
from engine.entities import Enemy, Player
from engine.game import Game
from engine.potions import use_potion
from engine.relics import trigger_relic_on_combat_start


class PowerBuffTests(unittest.TestCase):
    def test_metallicize_grants_block_at_turn_end(self):
        player = Player("Hero", 50)
        player.apply_buff("metallicize", 3)
        messages = player.trigger_turn_end_powers()
        self.assertEqual(player.block, 3)
        # Metallicize is permanent: it stays for the next turn.
        self.assertEqual(player.get_buff("metallicize"), 3)
        self.assertTrue(any("Metallicize" in m for m in messages))

    def test_metallicize_block_is_boosted_by_dexterity(self):
        player = Player("Hero", 50)
        player.apply_buff("metallicize", 3)
        player.apply_buff("dexterity", 2)
        player.trigger_turn_end_powers()
        self.assertEqual(player.block, 5)

    def test_regen_heals_and_counts_down(self):
        player = Player("Hero", 50)
        player.hp = 30
        player.apply_buff("regen", 4)
        player.trigger_turn_end_powers()
        self.assertEqual(player.hp, 34)
        self.assertEqual(player.get_buff("regen"), 3)

    def test_regen_does_not_overheal(self):
        player = Player("Hero", 50)
        player.hp = 48
        player.apply_buff("regen", 5)
        player.trigger_turn_end_powers()
        self.assertEqual(player.hp, 50)


class ThornsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = CardDatabase()
        cls.db.load_from_file("data/cards.json")

    def test_enemy_thorns_punish_a_card_attack(self):
        player = Player("Hero", 50)
        enemy = Enemy("Spiker", 30)
        enemy.apply_buff("thorns", 4)
        card = self.db.get_card("strike")  # 6 damage
        execute_effects(card.effects, player, enemy, [enemy])
        self.assertEqual(enemy.hp, 24)
        self.assertEqual(player.hp, 46)

    def test_player_thorns_punish_an_enemy_attack(self):
        player = Player("Hero", 50)
        enemy = Enemy("Slime", 30, actions=[{"type": "attack", "amount": 5}])
        game = Game(player, [enemy], self.db)
        game.setup_deck(["strike"] * 10)
        player.apply_buff("thorns", 3)
        game.enemy_turn()
        self.assertEqual(player.hp, 45)
        self.assertEqual(enemy.hp, 27)

    def test_thorns_does_not_retaliate_without_thorns(self):
        player = Player("Hero", 50)
        enemy = Enemy("Slime", 30)
        self.assertEqual(player.retaliate_thorns(enemy), 0)


class PowerContentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = CardDatabase()
        cls.db.load_from_file("data/cards.json")

    def test_bronze_scales_relic_grants_thorns_on_combat_start(self):
        player = Player("Hero", 50)
        game = Game(player, [Enemy("Slime", 30)], self.db, relics=["bronze_scales"])
        trigger_relic_on_combat_start("bronze_scales", game)
        self.assertEqual(player.get_buff("thorns"), 3)

    def test_regen_potion_applies_regen(self):
        player = Player("Hero", 50)
        game = Game(player, [Enemy("Slime", 30)], self.db)
        self.assertTrue(use_potion("regen_potion", game))
        self.assertEqual(player.get_buff("regen"), 5)

    def test_power_cards_apply_their_buffs(self):
        player = Player("Hero", 50)
        enemy = Enemy("Slime", 30)
        for card_id, buff in [("metallicize", "metallicize"), ("spiked_body", "thorns"), ("self_repair", "regen")]:
            card = self.db.get_card(card_id)
            execute_effects(card.effects, player, enemy, [enemy])
            self.assertGreater(player.get_buff(buff), 0, f"{card_id} should grant {buff}")


class BarricadeAndBlockTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = CardDatabase()
        cls.db.load_from_file("data/cards.json")

    def _game(self):
        player = Player("Hero", 60)
        game = Game(player, [Enemy("Slime", 30)], self.db)
        game.setup_deck(["defend"] * 10)
        return game, player

    def test_block_resets_normally_at_turn_start(self):
        game, player = self._game()
        player.add_block(15)
        game.start_player_turn()
        self.assertEqual(player.block, 0)

    def test_barricade_retains_block_at_turn_start(self):
        game, player = self._game()
        player.apply_buff("barricade", 1)
        player.add_block(15)
        game.start_player_turn()
        self.assertEqual(player.block, 15)

    def test_entrench_doubles_block(self):
        game, player = self._game()
        player.add_block(8)
        card = self.db.get_card("entrench")
        execute_effects(card.effects, player, game.enemies[0], game.enemies)
        self.assertEqual(player.block, 16)

    def test_barricade_card_grants_the_buff(self):
        player = Player("Hero", 60)
        enemy = Enemy("Slime", 30)
        card = self.db.get_card("barricade")
        execute_effects(card.effects, player, enemy, [enemy])
        self.assertEqual(player.get_buff("barricade"), 1)

    def test_body_slam_deals_damage_equal_to_block(self):
        player = Player("Hero", 60)
        enemy = Enemy("Slime", 30)
        player.add_block(12)
        card = self.db.get_card("body_slam")
        execute_effects(card.effects, player, enemy, [enemy])
        self.assertEqual(enemy.hp, 18)

    def test_body_slam_scales_after_entrench(self):
        player = Player("Hero", 60)
        enemy = Enemy("Slime", 40)
        player.add_block(8)
        execute_effects(self.db.get_card("entrench").effects, player, enemy, [enemy])  # block -> 16
        execute_effects(self.db.get_card("body_slam").effects, player, enemy, [enemy])  # hit for 16
        self.assertEqual(enemy.hp, 24)

    def test_body_slam_benefits_from_strength_and_vulnerable(self):
        player = Player("Hero", 60)
        enemy = Enemy("Slime", 40)
        player.add_block(10)
        player.apply_buff("strength", 2)       # 10 + 2 = 12
        enemy.apply_buff("vulnerable", 1)       # 12 * 1.5 = 18
        execute_effects(self.db.get_card("body_slam").effects, player, enemy, [enemy])
        self.assertEqual(enemy.hp, 22)


class RedSkullRelicTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = CardDatabase()
        cls.db.load_from_file("data/cards.json")

    def _game(self, hp):
        player = Player("Hero", 80)
        player.hp = hp
        return Game(player, [Enemy("Slime", 30)], self.db), player

    def test_red_skull_grants_strength_when_low(self):
        game, player = self._game(40)  # exactly 50%
        trigger_relic_on_combat_start("red_skull", game)
        self.assertEqual(player.get_buff("strength"), 3)

    def test_red_skull_silent_when_healthy(self):
        game, player = self._game(60)
        trigger_relic_on_combat_start("red_skull", game)
        self.assertEqual(player.get_buff("strength"), 0)


if __name__ == "__main__":
    unittest.main()
