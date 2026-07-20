from copy import deepcopy


class Entity:
    def __init__(self, name: str, max_hp: int):
        self.name = name
        self.max_hp = max_hp
        self.hp = max_hp
        self.block = 0
        self.buffs = {}
        self.stance = "Neutral"

    def take_damage(self, amount: int):
        if self.get_buff("intangible") > 0 and amount > 0:
            amount = 1
        if self.block > 0:
            if amount >= self.block:
                amount -= self.block
                self.block = 0
            else:
                self.block -= amount
                amount = 0
        
        self.hp -= amount
        if self.hp < 0:
            self.hp = 0

    def lose_hp(self, amount: int):
        if self.get_buff("intangible") > 0 and amount > 0:
            amount = 1
        self.hp = max(0, self.hp - max(0, amount))

    def add_block(self, amount: int):
        if self.get_buff("frail") > 0:
            amount = int(amount * 0.75)
        dex = self.get_buff("dexterity")
        self.block += max(0, amount + dex)

    def heal(self, amount: int):
        self.hp += amount
        if self.hp > self.max_hp:
            self.hp = self.max_hp

    def reset_block(self):
        self.block = 0

    def reset_combat_state(self):
        self.block = 0
        self.buffs.clear()
        self.stance = "Neutral"
        
    def is_dead(self) -> bool:
        return self.hp <= 0

    def get_buff(self, name: str) -> int:
        return self.buffs.get(name, 0)

    def apply_buff(self, name: str, amount: int):
        debuffs = {"weak", "vulnerable", "frail", "poison"}
        if amount > 0 and name in debuffs:
            if self.get_buff("artifact") > 0:
                print(f"> {self.name}'s Artifact negates {name}!")
                self.apply_buff("artifact", -1)
                return

        if name in self.buffs:
            self.buffs[name] += amount
        else:
            self.buffs[name] = amount
            
        # If a buff goes to 0 or below, we can remove it immediately or leave it at 0.
        if self.buffs[name] <= 0:
            del self.buffs[name]

    def tick_buffs(self):
        # Decrease duration-based buffs.
        for buff in ["weak", "vulnerable", "frail", "intangible"]:
            if buff in self.buffs and self.buffs[buff] > 0:
                self.buffs[buff] -= 1
                if self.buffs[buff] <= 0:
                    del self.buffs[buff]

    def trigger_poison(self) -> int:
        amount = self.get_buff("poison")
        if amount <= 0:
            return 0
        self.lose_hp(amount)
        self.apply_buff("poison", -1)
        return amount

    def trigger_turn_end_powers(self) -> list:
        """Resolve persistent end-of-turn powers. Returns log messages."""
        messages = []
        metallicize = self.get_buff("metallicize")
        if metallicize > 0:
            self.add_block(metallicize)
            messages.append(f"{self.name} gains {metallicize} Block from Metallicize!")
        regen = self.get_buff("regen")
        if regen > 0:
            self.heal(regen)
            self.apply_buff("regen", -1)
            messages.append(f"{self.name} regenerates {regen} HP!")
        ritual = self.get_buff("ritual")
        if ritual > 0:
            self.apply_buff("strength", ritual)
            messages.append(f"{self.name} gains {ritual} Strength from Ritual!")
        return messages

    def retaliate_thorns(self, attacker) -> int:
        """If this entity has Thorns, deal that much back to a living attacker."""
        thorns = self.get_buff("thorns")
        if thorns > 0 and attacker is not None and attacker is not self and not attacker.is_dead():
            attacker.take_damage(thorns)
            return thorns
        return 0

    def to_dict(self):
        return {
            "name": self.name,
            "max_hp": self.max_hp,
            "hp": self.hp,
            "block": self.block,
            "buffs": self.buffs,
            "stance": self.stance
        }

class Player(Entity):
    def __init__(self, name: str, max_hp: int, max_energy: int = 3):
        super().__init__(name, max_hp)
        self.max_energy = max_energy
        self.energy = max_energy
        self.max_orb_slots = 3
        self.orbs = []

    def reset_energy(self):
        self.energy = self.max_energy

    def reset_combat_state(self):
        super().reset_combat_state()
        self.reset_energy()
        self.orbs.clear()

    def spend_energy(self, amount: int) -> bool:
        if self.energy >= amount:
            self.energy -= amount
            return True
        return False

    def to_dict(self):
        data = super().to_dict()
        data["energy"] = self.energy
        data["max_energy"] = self.max_energy
        data["orbs"] = self.orbs
        data["max_orb_slots"] = self.max_orb_slots
        return data

class Enemy(Entity):
    def __init__(self, name: str, max_hp: int, attack_damage: int = 5, actions: list = None, phases: list = None, passives: list = None):
        super().__init__(name, max_hp)
        self.attack_damage = attack_damage
        self.actions = deepcopy(actions) if actions else [{"type": "attack", "amount": attack_damage}]
        self.action_index = 0
        self.phases = deepcopy(phases) if phases else []
        self.passives = deepcopy(passives) if passives else []
        self.phase_index = 0
        self.phase_name = None
        self.intent = self._format_intent(self.current_action)

    def take_damage(self, amount: int):
        old_hp = self.hp
        super().take_damage(amount)
        if "Asleep" in self.passives and self.hp < old_hp:
            print(f"> {self.name} wakes up!")
            self.passives.remove("Asleep")
            while self.actions[self.action_index].get("type") == "sleep":
                self.action_index = (self.action_index + 1) % len(self.actions)
            self.intent = self._format_intent(self.current_action)
        self._check_phase_transition()

    def lose_hp(self, amount: int):
        super().lose_hp(amount)
        self._check_phase_transition()

    @property
    def current_action(self) -> dict:
        return self.actions[self.action_index]

    def advance_intent(self):
        if "Asleep" in self.passives and self.actions[self.action_index].get("type") == "sleep":
            # If asleep and sleeping, decrement sleep duration by advancing, but what if duration ends?
            # We can let the action list be e.g. sleep, sleep, sleep, then it naturally wakes up.
            self.action_index = (self.action_index + 1) % len(self.actions)
            if self.actions[self.action_index].get("type") != "sleep":
                print(f"> {self.name} wakes up naturally!")
                self.passives.remove("Asleep")
        else:
            self.action_index = (self.action_index + 1) % len(self.actions)
            while "Asleep" not in self.passives and self.actions[self.action_index].get("type") == "sleep":
                self.action_index = (self.action_index + 1) % len(self.actions)
        self.intent = self._format_intent(self.current_action)

    def _format_intent(self, action: dict, target: Entity = None) -> str:
        action_type = action.get("type")
        amount = action.get("amount", 0)
        if action_type == "sleep":
            return "Zzz..."
        if action_type == "attack":
            amount += self.get_buff("strength")
            if self.get_buff("weak") > 0:
                amount = int(amount * 0.75)
            if target and target.get_buff("vulnerable") > 0:
                amount = int(amount * 1.5)
            return f"Attack {amount}"
        if action_type == "block":
            return f"Block {amount}"
        if action_type == "strength":
            return f"Gain {amount} Strength"
        if action_type == "buff":
            return f"Gain {action.get('buff', 'Power').title()}"
        if action_type == "debuff":
            return f"Apply {action.get('buff', 'Debuff').title()}"
        return action_type.title() if action_type else "Unknown"

    def set_intent(self, intent: str):
        self.intent = intent

    def _check_phase_transition(self):
        while self.phase_index < len(self.phases) and not self.is_dead():
            phase = self.phases[self.phase_index]
            if self.hp > self.max_hp * phase.get("threshold", 0):
                break
            self.phase_index += 1
            self.phase_name = phase.get("name")
            if phase.get("actions"):
                self.actions = deepcopy(phase["actions"])
                self.action_index = 0
            if phase.get("block"):
                self.add_block(phase["block"])
            if phase.get("strength"):
                self.apply_buff("strength", phase["strength"])
            self.intent = self._format_intent(self.current_action)
            print(f"> {self.name} enters {self.phase_name or 'a new phase'}!")

    def to_dict(self, target: Entity = None):
        data = super().to_dict()
        self.intent = self._format_intent(self.current_action, target)
        data["intent"] = self.intent
        data["attack_damage"] = self.attack_damage
        data["action"] = self.current_action
        data["phase_name"] = self.phase_name
        data["passives"] = self.passives
        return data

    def on_card_played(self, card: dict):
        if "Enrage" in self.passives and card.get("type") == "Skill":
            print(f"> {self.name}'s Enrage triggers!")
            self.apply_buff("strength", 2)

    def to_save_dict(self):
        data = super().to_dict()
        data["attack_damage"] = self.attack_damage
        data["actions"] = deepcopy(self.actions)
        data["action_index"] = self.action_index
        data["phases"] = deepcopy(self.phases)
        data["phase_index"] = self.phase_index
        data["phase_name"] = self.phase_name
        data["passives"] = deepcopy(self.passives)
        return data

    @classmethod
    def from_save_dict(cls, data: dict):
        enemy = cls(
            data["name"],
            data["max_hp"],
            data.get("attack_damage", 5),
            data.get("actions"),
            data.get("phases"),
            data.get("passives"),
        )
        enemy.hp = data.get("hp", enemy.max_hp)
        enemy.block = data.get("block", 0)
        enemy.buffs = deepcopy(data.get("buffs", {}))
        enemy.action_index = data.get("action_index", 0) % len(enemy.actions)
        enemy.phase_index = data.get("phase_index", 0)
        enemy.phase_name = data.get("phase_name")
        enemy.intent = enemy._format_intent(enemy.current_action)
        return enemy
