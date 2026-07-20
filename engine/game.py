from engine.entities import Player, Enemy
from engine.cards import CardPile
from engine.effects import calculate_damage, execute_effects
from engine.database import CardDatabase
from engine.relics import (
    trigger_relic_on_combat_start,
    trigger_relic_on_card_play,
    trigger_relic_on_turn_end,
    trigger_relic_on_take_damage,
)

class Game:
    def __init__(self, player: Player, enemies: list, db: CardDatabase, relics: list = None):
        self.player = player
        self.enemies = enemies
        self.db = db
        self.relics = relics or []
        
        self.deck = CardPile()
        self.hand = CardPile()
        self.discard = CardPile()
        self.exhaust = CardPile()
        self.powers = CardPile()
        
        self.turn = 0
        self.cards_drawn_per_turn = 5

    def setup_deck(self, card_ids: list):
        for cid in card_ids:
            card = self.db.get_card(cid)
            if card:
                self.deck.add(card)
        self.deck.shuffle()

    def start_combat(self):
        print(f"\n--- Combat Starts ---")
        self.start_player_turn()
        for r_id in self.relics:
            trigger_relic_on_combat_start(r_id, self)

    def draw_cards(self, amount: int):
        for _ in range(amount):
            if self.deck.is_empty():
                if self.discard.is_empty():
                    break # No more cards to draw at all
                # Shuffle discard into deck
                print("> Shuffling discard pile into deck...")
                self.deck.cards = self.discard.get_all()[:]
                self.discard.clear()
                self.deck.shuffle()
            card = self.deck.draw()
            if card:
                self.hand.add(card)

    def start_player_turn(self):
        self.turn += 1
        print(f"\n=== Turn {self.turn} ===")
        poison_damage = self.player.trigger_poison()
        if poison_damage:
            print(f"> {self.player.name} takes {poison_damage} poison damage!")
        if self.player.is_dead():
            return
        self.player.reset_energy()
        if self.player.get_buff("barricade") <= 0:
            self.player.reset_block()
        self.draw_cards(self.cards_drawn_per_turn)

    def play_card(self, hand_index: int, target_index: int = 0) -> bool:
        if hand_index < 0 or hand_index >= len(self.hand):
            print("Invalid card index.")
            return False

        card = self.hand.cards[hand_index]

        target = None
        if 0 <= target_index < len(self.enemies) and not self.enemies[target_index].is_dead():
            target = self.enemies[target_index]
        elif self._requires_target(card):
            target = next((enemy for enemy in self.enemies if not enemy.is_dead()), None)
            if not target:
                print("No valid target.")
                return False

        x = 0
        if card.cost == "X":
            x = self.player.energy
            self.player.energy = 0
            paid = True
        else:
            paid = self.player.spend_energy(card.cost)

        if paid:
            print(f"\n> {self.player.name} plays {card.name}!")
            self.hand.cards.pop(hand_index)

            for r_id in self.relics:
                trigger_relic_on_card_play(r_id, self, card)

            for enemy in self.enemies:
                if not enemy.is_dead():
                    enemy.on_card_played(card.to_dict())

            # Apply effects
            execute_effects(
                card.effects,
                self.player,
                target,
                self.enemies,
                self.draw_cards,
                self.channel_orb,
                self.evoke_orb,
                x=x,
            )
            if card.type == "Power":
                self.powers.add(card)
            elif card.exhaust:
                self.exhaust.add(card)
            else:
                self.discard.add(card)
            return True
        else:
            print("Not enough energy!")
            return False

    def _requires_target(self, card) -> bool:
        target_effects = {"damage", "apply_buff", "poison"}
        return any(
            effect.get("type") in target_effects and effect.get("target", "target") == "target"
            for effect in card.effects
        )

    def end_player_turn(self):
        print(f"\n> {self.player.name} ends their turn.")
        for r_id in self.relics:
            trigger_relic_on_turn_end(r_id, self)
        # Discard hand
        for card in self.hand.get_all():
            self.discard.add(card)
        self.hand.clear()
        self.player.tick_buffs()
        for message in self.player.trigger_turn_end_powers():
            print(f"> {message}")
        self.trigger_orb_passives()

        if self.is_game_over():
            return

        self.enemy_turn()

    def enemy_turn(self):
        print("\n--- Enemies' Turn ---")
        for enemy in self.enemies:
            if enemy.is_dead():
                continue
            enemy.reset_block()
            poison_damage = enemy.trigger_poison()
            if poison_damage:
                print(f"> {enemy.name} takes {poison_damage} poison damage!")
            if enemy.is_dead():
                continue

            action = enemy.current_action
            amount = action.get("amount", 0)
            if action.get("type") == "attack":
                damage = calculate_damage(amount, enemy, self.player)
                for r_id in self.relics:
                    damage = trigger_relic_on_take_damage(r_id, self, damage)
                print(f"> {enemy.name} attacks for {damage} damage!")
                self.player.take_damage(damage)
                thorns = self.player.retaliate_thorns(enemy)
                if thorns:
                    print(f"> {self.player.name}'s Thorns deals {thorns} damage to {enemy.name}!")
            elif action.get("type") == "block":
                enemy.add_block(amount)
                print(f"> {enemy.name} gains {amount} block!")
            elif action.get("type") == "strength":
                enemy.apply_buff("strength", amount)
                print(f"> {enemy.name} gains {amount} strength!")
            elif action.get("type") == "buff":
                buff_name = action.get("buff")
                enemy.apply_buff(buff_name, amount)
                print(f"> {enemy.name} gains {amount} {buff_name}!")
            elif action.get("type") == "debuff":
                buff_name = action.get("buff")
                self.player.apply_buff(buff_name, amount)
                print(f"> {enemy.name} applies {amount} {buff_name} to {self.player.name}!")
            enemy.tick_buffs()
            for message in enemy.trigger_turn_end_powers():
                print(f"> {message}")
            enemy.advance_intent()
            if self.player.is_dead():
                break

        if not self.player.is_dead():
            self.start_player_turn()

    def channel_orb(self, orb_type: str):
        if len(self.player.orbs) >= self.player.max_orb_slots:
            self.evoke_orb()
        self.player.orbs.append(orb_type)

    def evoke_orb(self, times: int = 1):
        if not self.player.orbs:
            return
        orb_type = self.player.orbs.pop(0)
        for _ in range(times):
            self._activate_orb(orb_type, evoked=True)

    def trigger_orb_passives(self):
        for orb_type in self.player.orbs[:]:
            self._activate_orb(orb_type, evoked=False)

    def _activate_orb(self, orb_type: str, evoked: bool):
        if orb_type == "lightning":
            target = next((enemy for enemy in self.enemies if not enemy.is_dead()), None)
            if not target:
                return
            damage = 8 if evoked else 3
            target.take_damage(damage)
            print(f"> Lightning orb deals {damage} damage to {target.name}!")
        elif orb_type == "frost":
            block = 5 if evoked else 2
            self.player.add_block(block)
            print(f"> Frost orb grants {block} block!")

    def is_game_over(self) -> bool:
        if self.player.is_dead():
            return True
        return all(enemy.is_dead() for enemy in self.enemies)

    def to_save_dict(self):
        return {
            "enemies": [enemy.to_save_dict() for enemy in self.enemies],
            "deck": [card.id for card in self.deck.get_all()],
            "hand": [card.id for card in self.hand.get_all()],
            "discard": [card.id for card in self.discard.get_all()],
            "exhaust": [card.id for card in self.exhaust.get_all()],
            "powers": [card.id for card in self.powers.get_all()],
            "turn": self.turn,
            "cards_drawn_per_turn": self.cards_drawn_per_turn,
        }

    @classmethod
    def from_save_dict(cls, player: Player, data: dict, db: CardDatabase, relics: list = None):
        enemies = [Enemy.from_save_dict(enemy_data) for enemy_data in data.get("enemies", [])]
        game = cls(player, enemies, db, relics)
        game.deck = CardPile(game._restore_cards(data.get("deck", [])))
        game.hand = CardPile(game._restore_cards(data.get("hand", [])))
        game.discard = CardPile(game._restore_cards(data.get("discard", [])))
        game.exhaust = CardPile(game._restore_cards(data.get("exhaust", [])))
        game.powers = CardPile(game._restore_cards(data.get("powers", [])))
        game.turn = data.get("turn", 0)
        game.cards_drawn_per_turn = data.get("cards_drawn_per_turn", 5)
        return game

    def _restore_cards(self, card_ids: list):
        return [card for card_id in card_ids if (card := self.db.get_card(card_id))]

    def to_dict(self):
        return {
            "player": self.player.to_dict(),
            "enemies": [e.to_dict(self.player) for e in self.enemies],
            "hand": [c.to_dict() for c in self.hand.get_all()],
            "deck": [c.to_dict() for c in self.deck.get_all()],
            "discard": [c.to_dict() for c in self.discard.get_all()],
            "exhaust": [c.to_dict() for c in self.exhaust.get_all()],
            "deck_size": len(self.deck),
            "discard_size": len(self.discard),
            "exhaust_size": len(self.exhaust),
            "powers": [c.to_dict() for c in self.powers.get_all()],
            "turn": self.turn,
            "game_over": self.is_game_over()
        }
