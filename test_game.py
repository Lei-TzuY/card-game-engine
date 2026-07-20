import unittest

from engine.database import CardDatabase
from engine.entities import Enemy, Player
from engine.game import Game


class GameTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = CardDatabase()
        cls.db.load_from_file("data/cards.json")

    def test_draw_effect_adds_card_to_hand(self):
        player = Player("Hero", 50)
        enemy = Enemy("Slime", 30)
        game = Game(player, [enemy], self.db)
        game.hand.add(self.db.get_card("pommel_strike"))
        game.deck.add(self.db.get_card("defend"))

        self.assertTrue(game.play_card(0))

        self.assertEqual(enemy.hp, 25)
        self.assertEqual([card.id for card in game.hand.get_all()], ["defend"])
        self.assertEqual([card.id for card in game.discard.get_all()], ["pommel_strike"])

    def test_enemy_weak_reduces_attack_then_expires(self):
        player = Player("Hero", 50)
        enemy = Enemy("Slime", 30, attack_damage=8)
        enemy.apply_buff("weak", 1)
        game = Game(player, [enemy], self.db)

        game.enemy_turn()

        self.assertEqual(player.hp, 44)
        self.assertEqual(enemy.get_buff("weak"), 0)
        self.assertEqual(enemy.intent, "Attack 8")

    def test_dead_default_target_falls_back_to_living_enemy(self):
        player = Player("Hero", 50)
        dead_enemy = Enemy("Dead Slime", 1)
        living_enemy = Enemy("Living Slime", 30)
        dead_enemy.take_damage(1)
        game = Game(player, [dead_enemy, living_enemy], self.db)
        game.hand.add(self.db.get_card("strike"))

        self.assertTrue(game.play_card(0, target_index=0))

        self.assertEqual(living_enemy.hp, 24)

    def test_player_debuff_survives_until_player_finishes_turn(self):
        player = Player("Hero", 50)
        player.apply_buff("weak", 1)
        game = Game(player, [Enemy("Slime", 30)], self.db)

        game.start_player_turn()
        self.assertEqual(player.get_buff("weak"), 1)

        game.end_player_turn()
        self.assertEqual(player.get_buff("weak"), 0)

    def test_power_card_moves_to_power_zone(self):
        player = Player("Hero", 50)
        game = Game(player, [Enemy("Slime", 30)], self.db)
        game.hand.add(self.db.get_card("inflame"))

        self.assertTrue(game.play_card(0))

        self.assertEqual(player.get_buff("strength"), 2)
        self.assertEqual(len(game.powers), 1)
        self.assertEqual(len(game.discard), 0)

    def test_exhaust_card_moves_to_exhaust_pile(self):
        player = Player("Hero", 50)
        enemy = Enemy("Slime", 30)
        game = Game(player, [enemy], self.db)
        game.hand.add(self.db.get_card("intimidate"))

        self.assertTrue(game.play_card(0))

        self.assertEqual(enemy.get_buff("weak"), 1)
        self.assertEqual(len(game.exhaust), 1)
        self.assertEqual(len(game.discard), 0)

    def test_upgraded_card_uses_improved_effect(self):
        player = Player("Hero", 50)
        enemy = Enemy("Slime", 30)
        game = Game(player, [enemy], self.db)
        upgraded_strike = self.db.get_card("strike+")
        game.hand.add(upgraded_strike)

        self.assertTrue(upgraded_strike.upgraded)
        self.assertEqual(upgraded_strike.name, "Strike+")
        self.assertTrue(game.play_card(0))
        self.assertEqual(enemy.hp, 21)

    def test_poison_bypasses_block_and_decreases_before_enemy_action(self):
        player = Player("Hero", 50)
        enemy = Enemy("Slime", 30, attack_damage=5)
        enemy.add_block(20)
        enemy.apply_buff("poison", 3)
        game = Game(player, [enemy], self.db)

        game.enemy_turn()

        self.assertEqual(enemy.hp, 27)
        self.assertEqual(enemy.get_buff("poison"), 2)
        self.assertEqual(player.hp, 45)

    def test_poison_kill_prevents_enemy_action(self):
        player = Player("Hero", 50)
        enemy = Enemy("Slime", 3, attack_damage=20)
        enemy.apply_buff("poison", 3)
        game = Game(player, [enemy], self.db)

        game.enemy_turn()

        self.assertTrue(enemy.is_dead())
        self.assertEqual(player.hp, 50)

    def test_enemy_cycles_between_block_and_attack_intents(self):
        player = Player("Hero", 50)
        enemy = Enemy(
            "Guard",
            30,
            actions=[
                {"type": "block", "amount": 5},
                {"type": "attack", "amount": 7},
            ],
        )
        game = Game(player, [enemy], self.db)

        game.enemy_turn()
        self.assertEqual(enemy.block, 5)
        self.assertEqual(enemy.intent, "Attack 7")
        self.assertEqual(player.hp, 50)

        game.enemy_turn()
        self.assertEqual(enemy.block, 0)
        self.assertEqual(enemy.intent, "Block 5")
        self.assertEqual(player.hp, 43)

    def test_enemy_strength_action_increases_later_attack(self):
        player = Player("Hero", 50)
        enemy = Enemy(
            "Cultist",
            30,
            actions=[
                {"type": "strength", "amount": 2},
                {"type": "attack", "amount": 6},
            ],
        )
        game = Game(player, [enemy], self.db)

        game.enemy_turn()
        self.assertEqual(enemy.get_buff("strength"), 2)
        self.assertEqual(enemy.intent, "Attack 8")

        game.enemy_turn()
        self.assertEqual(player.hp, 42)

    def test_serialized_intent_reflects_weak_and_target_vulnerable(self):
        player = Player("Hero", 50)
        player.apply_buff("vulnerable", 1)
        enemy = Enemy("Slime", 30, attack_damage=8)
        enemy.apply_buff("weak", 1)

        self.assertEqual(enemy.to_dict(player)["intent"], "Attack 9")

    def test_lightning_orb_passive_deals_damage(self):
        player = Player("Defect", 75)
        enemy = Enemy("Slime", 30)
        game = Game(player, [enemy], self.db)
        game.channel_orb("lightning")

        game.trigger_orb_passives()

        self.assertEqual(enemy.hp, 27)
        self.assertEqual(player.orbs, ["lightning"])

    def test_frost_orb_passive_and_evoke_grant_block(self):
        player = Player("Defect", 75)
        game = Game(player, [Enemy("Slime", 30)], self.db)
        game.channel_orb("frost")

        game.trigger_orb_passives()
        self.assertEqual(player.block, 2)

        game.evoke_orb()
        self.assertEqual(player.block, 7)
        self.assertEqual(player.orbs, [])

    def test_channeling_into_full_slots_evokes_oldest_orb(self):
        player = Player("Defect", 75)
        enemy = Enemy("Slime", 30)
        game = Game(player, [enemy], self.db)
        player.orbs = ["lightning", "frost", "frost"]

        game.channel_orb("lightning")

        self.assertEqual(enemy.hp, 22)
        self.assertEqual(player.orbs, ["frost", "frost", "lightning"])

    def test_dualcast_evokes_same_orb_twice(self):
        player = Player("Defect", 75)
        enemy = Enemy("Slime", 30)
        game = Game(player, [enemy], self.db)
        game.channel_orb("lightning")
        game.hand.add(self.db.get_card("dualcast"))

        self.assertTrue(game.play_card(0))

        self.assertEqual(enemy.hp, 14)
        self.assertEqual(player.orbs, [])

    def test_zap_does_not_require_enemy_target(self):
        player = Player("Defect", 75)
        game = Game(player, [], self.db)
        game.hand.add(self.db.get_card("zap"))

        self.assertTrue(game.play_card(0))
        self.assertEqual(player.orbs, ["lightning"])

    def test_anchor_relic_grants_block_after_first_turn_setup(self):
        player = Player("Hero", 50)
        game = Game(player, [Enemy("Slime", 30)], self.db, relics=["anchor"])

        game.start_combat()

        self.assertEqual(player.block, 10)

    def test_combat_snapshot_restores_enemy_and_card_piles(self):
        player = Player("Hero", 50)
        enemy = Enemy(
            "Guard",
            30,
            actions=[
                {"type": "block", "amount": 5},
                {"type": "attack", "amount": 7},
            ],
        )
        enemy.hp = 19
        enemy.block = 4
        enemy.apply_buff("strength", 2)
        enemy.action_index = 1
        game = Game(player, [enemy], self.db)
        game.deck.add(self.db.get_card("strike+"))
        game.hand.add(self.db.get_card("defend"))
        game.discard.add(self.db.get_card("pommel_strike"))
        game.exhaust.add(self.db.get_card("intimidate"))
        game.powers.add(self.db.get_card("inflame"))
        game.turn = 3

        restored = Game.from_save_dict(player, game.to_save_dict(), self.db)

        restored_enemy = restored.enemies[0]
        self.assertEqual(restored_enemy.hp, 19)
        self.assertEqual(restored_enemy.block, 4)
        self.assertEqual(restored_enemy.get_buff("strength"), 2)
        self.assertEqual(restored_enemy.action_index, 1)
        self.assertEqual(restored_enemy.current_action, {"type": "attack", "amount": 7})
        self.assertEqual([card.id for card in restored.deck.get_all()], ["strike+"])
        self.assertEqual([card.id for card in restored.hand.get_all()], ["defend"])
        self.assertEqual([card.id for card in restored.discard.get_all()], ["pommel_strike"])
        self.assertEqual([card.id for card in restored.exhaust.get_all()], ["intimidate"])
        self.assertEqual([card.id for card in restored.powers.get_all()], ["inflame"])
        self.assertEqual(restored.turn, 3)

    def test_boss_phase_transition_changes_pattern_and_survives_snapshot(self):
        player = Player("Hero", 50)
        enemy = Enemy(
            "Boss",
            40,
            actions=[{"type": "attack", "amount": 6}],
            phases=[
                {
                    "threshold": 0.5,
                    "name": "Rage",
                    "block": 10,
                    "strength": 2,
                    "actions": [{"type": "attack", "amount": 12}],
                }
            ],
        )
        game = Game(player, [enemy], self.db)

        enemy.take_damage(21)

        self.assertEqual(enemy.hp, 19)
        self.assertEqual(enemy.block, 10)
        self.assertEqual(enemy.get_buff("strength"), 2)
        self.assertEqual(enemy.phase_name, "Rage")
        self.assertEqual(enemy.intent, "Attack 14")

        restored = Game.from_save_dict(player, game.to_save_dict(), self.db)
        restored_enemy = restored.enemies[0]
        self.assertEqual(restored_enemy.phase_name, "Rage")
        self.assertEqual(restored_enemy.phase_index, 1)
        self.assertEqual(restored_enemy.block, 10)
        self.assertEqual(restored_enemy.get_buff("strength"), 2)

        restored_enemy.take_damage(1)
        self.assertEqual(restored_enemy.block, 9)
        self.assertEqual(restored_enemy.get_buff("strength"), 2)

    def test_poison_can_trigger_boss_phase_transition(self):
        enemy = Enemy(
            "Boss",
            20,
            phases=[
                {
                    "threshold": 0.5,
                    "name": "Rage",
                    "actions": [{"type": "attack", "amount": 12}],
                }
            ],
        )
        enemy.apply_buff("poison", 11)

        enemy.trigger_poison()

        self.assertEqual(enemy.hp, 9)
        self.assertEqual(enemy.phase_name, "Rage")
        self.assertEqual(enemy.current_action, {"type": "attack", "amount": 12})


if __name__ == "__main__":
    unittest.main()
