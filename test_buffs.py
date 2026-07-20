import unittest

from engine.database import CardDatabase
from engine.effects import execute_effects
from engine.entities import Enemy, Player


class BuffEffectTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = CardDatabase()
        cls.db.load_from_file("data/cards.json")

    def setUp(self):
        self.player = Player("Hero", 50)
        self.enemy = Enemy("Slime", 50)

    def execute(self, card_id):
        card = self.db.get_card(card_id)
        execute_effects(card.effects, self.player, self.enemy, [self.enemy])

    def test_strength_increases_damage(self):
        self.execute("inflame")
        self.execute("strike")

        self.assertEqual(self.player.get_buff("strength"), 2)
        self.assertEqual(self.enemy.hp, 42)

    def test_uppercut_applies_weak_and_vulnerable(self):
        self.execute("uppercut")

        self.assertEqual(self.enemy.hp, 37)
        self.assertEqual(self.enemy.get_buff("weak"), 1)
        self.assertEqual(self.enemy.get_buff("vulnerable"), 1)

    def test_bash_applies_vulnerable(self):
        self.execute("bash")

        self.assertEqual(self.enemy.hp, 42)
        self.assertEqual(self.enemy.get_buff("vulnerable"), 2)

    def test_vulnerable_increases_damage_and_expires(self):
        self.enemy.apply_buff("vulnerable", 1)
        self.execute("strike")
        self.enemy.tick_buffs()

        self.assertEqual(self.enemy.hp, 41)
        self.assertEqual(self.enemy.get_buff("vulnerable"), 0)

    def test_deadly_poison_applies_poison(self):
        self.execute("deadly_poison")

        self.assertEqual(self.enemy.hp, 50)
        self.assertEqual(self.enemy.get_buff("poison"), 5)


if __name__ == "__main__":
    unittest.main()
