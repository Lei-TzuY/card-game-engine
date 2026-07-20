from typing import List
from engine.entities import Entity

def calculate_damage(amount: int, source: Entity, target: Entity) -> int:
    final_damage = amount + source.get_buff("strength")
    if source.get_buff("weak") > 0:
        final_damage = int(final_damage * 0.75)
    if source.stance == "Wrath":
        final_damage = int(final_damage * 2)
    if source.get_buff("pen_nib_active") > 0:
        final_damage = int(final_damage * 2)
    
    if target.get_buff("vulnerable") > 0:
        final_damage = int(final_damage * 1.5)
    if target.stance == "Wrath":
        final_damage = int(final_damage * 2)
        
    return max(0, final_damage)

def execute_effects(
    effects_dsl: List[dict],
    source: Entity,
    selected_target: Entity,
    all_enemies: List[Entity],
    draw_cards=None,
    channel_orb=None,
    evoke_orb=None,
    x: int = 0,
):
    """
    A simple interpreter for the card effect DSL.

    `x` is the energy paid for an X-cost card. Effects flagged with
    "per_energy": true are applied that many times (0 when x is 0).
    """
    for effect in effects_dsl:
        repeats = x if effect.get("per_energy") else 1
        for _ in range(repeats):
            _apply_effect(effect, source, selected_target, all_enemies, draw_cards, channel_orb, evoke_orb)

    if source.get_buff("pen_nib_active") > 0:
        del source.buffs["pen_nib_active"]


def _apply_effect(effect, source, selected_target, all_enemies, draw_cards, channel_orb, evoke_orb):
    effect_type = effect.get("type")
    amount = effect.get("amount", 0)
    target_str = effect.get("target", "target")  # "target" (default), "source", "all_enemies"

    # Determine the actual targets for this specific effect
    actual_targets = []
    if target_str == "source":
        actual_targets = [source]
    elif target_str == "all_enemies":
        actual_targets = [e for e in all_enemies if not e.is_dead()]
    else:  # "target" or default single target
        if selected_target and not selected_target.is_dead():
            actual_targets = [selected_target]

    for target in actual_targets:
        if effect_type == "damage":
            final_damage = calculate_damage(amount, source, target)
            target.take_damage(final_damage)
            print(f"> {source.name} deals {final_damage} damage to {target.name}!")
            thorns = target.retaliate_thorns(source)
            if thorns:
                print(f"> {target.name}'s Thorns deals {thorns} damage to {source.name}!")

        elif effect_type == "block":
            target.add_block(amount)
            print(f"> {target.name} gains {amount} block!")

        elif effect_type == "double_block":
            target.block *= 2
            print(f"> {target.name}'s Block is doubled to {target.block}!")

        elif effect_type == "block_damage":
            final_damage = calculate_damage(source.block, source, target)
            target.take_damage(final_damage)
            print(f"> {source.name} slams for {final_damage} damage to {target.name}!")
            thorns = target.retaliate_thorns(source)
            if thorns:
                print(f"> {target.name}'s Thorns deals {thorns} damage to {source.name}!")

        elif effect_type == "heal":
            target.heal(amount)
            print(f"> {target.name} heals for {amount} HP!")

        elif effect_type == "apply_buff":
            buff_name = effect.get("buff", "unknown")
            target.apply_buff(buff_name, amount)
            print(f"> {target.name} gains {amount} {buff_name}!")

        elif effect_type == "remove_buff":
            buff_name = effect.get("buff", "unknown")
            if buff_name in target.buffs:
                del target.buffs[buff_name]
                print(f"> {target.name} loses {buff_name}!")

        elif effect_type == "poison":
            target.apply_buff("poison", amount)
            print(f"> {target.name} gains {amount} poison!")

        elif effect_type == "gain_energy":
            if hasattr(target, "energy"):
                target.energy += amount
                print(f"> {target.name} gains {amount} energy!")

        elif effect_type == "change_stance":
            new_stance = effect.get("stance", "Neutral")
            if target.stance == "Calm" and new_stance != "Calm":
                if hasattr(target, "energy"):
                    target.energy += 2
                    print(f"> {target.name} leaves Calm and gains 2 energy!")
            target.stance = new_stance
            print(f"> {target.name} enters {new_stance} stance!")

    if effect_type == "draw" and draw_cards:
        draw_cards(amount)
        print(f"> {source.name} draws {amount} card(s)!")
    elif effect_type == "channel_orb" and channel_orb:
        orb_type = effect.get("orb", "lightning")
        channel_orb(orb_type)
        print(f"> {source.name} channels {orb_type}!")
    elif effect_type == "evoke_orb" and evoke_orb:
        evoke_orb(amount)
