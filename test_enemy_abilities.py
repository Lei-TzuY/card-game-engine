import unittest

from engine.database import CardDatabase
from engine.entities import Enemy, Player
from engine.game import Game
from engine.session import _validate_enemy_action


class EnemyActionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = CardDatabase()
        cls.db.load_from_file("data/cards.json")

    def _game(self, enemy):
        player = Player("Hero", 60)
        game = Game(player, [enemy], self.db)
        game.setup_deck(["strike"] * 10)
        return game, player

    def test_buff_action_applies_self_buff(self):
        enemy = Enemy("Bramble", 30, actions=[{"type": "buff", "buff": "thorns", "amount": 4},
                                              {"type": "attack", "amount": 5}])
        game, _ = self._game(enemy)
        game.enemy_turn()
        self.assertEqual(enemy.get_buff("thorns"), 4)

    def test_debuff_action_applies_to_player(self):
        enemy = Enemy("Witch", 30, actions=[{"type": "debuff", "buff": "weak", "amount": 2},
                                            {"type": "attack", "amount": 5}])
        game, player = self._game(enemy)
        game.enemy_turn()
        self.assertEqual(player.get_buff("weak"), 2)

    def test_enemy_buff_thorns_punishes_player_attack(self):
        enemy = Enemy("Bramble", 30, actions=[{"type": "buff", "buff": "thorns", "amount": 4}])
        game, player = self._game(enemy)
        game.enemy_turn()  # enemy gains 4 thorns
        index = next(i for i, c in enumerate(game.hand.cards) if c.id == "strike")
        game.play_card(index, 0)  # strike deals 6, takes 4 thorns back
        self.assertEqual(player.hp, 56)


class RitualPowerTests(unittest.TestCase):
    def test_ritual_grants_escalating_strength(self):
        enemy = Enemy("Cultist", 40)
        enemy.apply_buff("ritual", 2)
        enemy.trigger_turn_end_powers()
        self.assertEqual(enemy.get_buff("strength"), 2)
        enemy.trigger_turn_end_powers()
        self.assertEqual(enemy.get_buff("strength"), 4)
        # Ritual itself is permanent.
        self.assertEqual(enemy.get_buff("ritual"), 2)


class EnemyIntentTests(unittest.TestCase):
    def test_buff_and_debuff_intents_are_readable(self):
        buffer = Enemy("Cultist", 30, actions=[{"type": "buff", "buff": "ritual", "amount": 1}])
        self.assertIn("Ritual", buffer.intent)
        debuffer = Enemy("Witch", 30, actions=[{"type": "debuff", "buff": "weak", "amount": 2}])
        self.assertIn("Weak", debuffer.intent)


class EnemyActionValidationTests(unittest.TestCase):
    def test_valid_buff_and_debuff_actions_pass(self):
        _validate_enemy_action("ok", {"type": "buff", "buff": "ritual", "amount": 1})
        _validate_enemy_action("ok", {"type": "debuff", "buff": "vulnerable", "amount": 2})

    def test_unsupported_self_buff_is_rejected(self):
        with self.assertRaises(ValueError):
            _validate_enemy_action("bad", {"type": "buff", "buff": "poison", "amount": 1})

    def test_debuff_must_be_a_real_debuff(self):
        with self.assertRaises(ValueError):
            _validate_enemy_action("bad", {"type": "debuff", "buff": "strength", "amount": 1})

    def test_buff_action_requires_amount_and_name(self):
        with self.assertRaises(ValueError):
            _validate_enemy_action("bad", {"type": "buff", "buff": "ritual", "amount": 0})
        with self.assertRaises(ValueError):
            _validate_enemy_action("bad", {"type": "buff", "buff": "", "amount": 1})


if __name__ == "__main__":
    unittest.main()
