import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from engine.database import CardDatabase
from engine.entities import Player, Enemy
from engine.game import Game
from engine.session import Session
from engine.characters import list_characters, get_character
from engine.events import EVENTS_DB
from engine.potions import POTIONS_DB
from engine.relics import RELICS_DB


db = CardDatabase()
try:
    db.load_from_file("data/cards.json")
except Exception as e:
    print(f"Error loading cards: {e}")
    sys.exit(1)


def clr():
    os.system('cls' if os.name == 'nt' else 'clear')


def fmt_buffs(buffs):
    return ", ".join(f"{k}:{v}" for k, v in buffs.items()) if buffs else "none"


def select_character() -> str:
    while True:
        clr()
        print("╔══════════════════════════════╗")
        print("║   CARD GAME ENGINE — START   ║")
        print("╚══════════════════════════════╝\n")
        chars = list_characters()
        for i, (cid, cdef) in enumerate(chars, 1):
            print(f"  [{i}] {cdef['name']:<12} HP:{cdef['max_hp']:>3}  — {cdef['description']}")
        print("\nChoose a character (1-3): ", end="", flush=True)
        choice = input().strip()
        if choice.isdigit() and 1 <= int(choice) <= len(chars):
            return chars[int(choice) - 1][0]


def print_map(session: Session):
    print("\n=== MAP ===")
    max_floor = max(n.floor for n in session.map_nodes)
    for floor in range(1, max_floor + 1):
        nodes = [n for n in session.map_nodes if n.floor == floor]
        row = []
        for n in nodes:
            avail = n.id in session.available_node_ids and not n.completed
            done  = n.completed
            sym = {"Enemy": "⚔", "Elite": "☠", "Rest": "♥", "Shop": "$", "Event": "?", "Boss": "★"}.get(n.type, "?")
            tag = f"[{n.id}:{sym}]" if avail else (f"({n.id}:{sym})" if done else f"_{n.id}:{sym}_")
            row.append(tag)
        print(f"  Floor {floor:>2}: {' '.join(row)}")
    print(f"\nFloor: {session.floor}/{max_floor}  Gold: {session.gold}g  HP: {session.player.hp}/{session.player.max_hp}")
    avail = [n for n in session.map_nodes if n.id in session.available_node_ids and not n.completed]
    if avail:
        descs = ", ".join(f"{n.id}({n.type})" for n in avail)
        print(f"Available: {descs}")


def print_combat(session: Session, game: Game):
    clr()
    print("=== COMBAT ===\n")
    for i, e in enumerate(game.enemies):
        status = "☠ DEAD" if e.is_dead() else f"HP:{e.hp}/{e.max_hp} BLK:{e.block} [{fmt_buffs(e.buffs)}]"
        print(f"  Enemy {i}: {e.name}  {status}  Intent:{e.intent}")
    print()
    p = session.player
    print(f"  Player: {p.name}  HP:{p.hp}/{p.max_hp}  BLK:{p.block}  Energy:{p.energy}/{p.max_energy}")
    print(f"  Buffs: {fmt_buffs(p.buffs)}")
    print(f"  Orbs: {', '.join(p.orbs) if p.orbs else 'none'}")
    potion_names = [POTIONS_DB[potion_id]["name"] for potion_id in session.potions if potion_id in POTIONS_DB]
    print(f"  Potions: {', '.join(potion_names) if potion_names else 'none'}")
    print(f"  Deck:{len(game.deck)}  Discard:{len(game.discard)}  Exhaust:{len(game.exhaust)}  Powers:{len(game.powers)}")
    print("\n  Hand:")
    for i, c in enumerate(game.hand.get_all()):
        print(f"    [{i}] {c.name}  (cost {c.cost})")
    print()


def run_combat(session: Session, node) -> bool:
    enemies = [Enemy(e["name"], e["hp"], e.get("attack", 5), e.get("actions"), e.get("phases")) for e in node.enemies_data]
    game = Game(session.player, enemies, db, session.relics)
    game.setup_deck(session.master_deck)
    game.start_combat()

    while not game.is_game_over():
        print_combat(session, game)
        cmd = input("  Action (play <i> [target], potion <i> [target], end, quit): ").strip().lower()
        if cmd == "quit":
            return False
        elif cmd == "end":
            game.end_player_turn()
        elif cmd.startswith("play"):
            parts = cmd.split()
            if len(parts) >= 2 and parts[1].isdigit():
                idx = int(parts[1])
                target = int(parts[2]) if len(parts) >= 3 and parts[2].isdigit() else 0
                game.play_card(idx, target)
            else:
                print("  Usage: play <card_index> [target_index]")
                input("  Enter to continue...")
        elif cmd.startswith("potion"):
            parts = cmd.split()
            if len(parts) >= 2 and parts[1].isdigit():
                idx = int(parts[1])
                target = int(parts[2]) if len(parts) >= 3 and parts[2].isdigit() else 0
                if not session.use_potion(idx, game, target):
                    print("  Potion unavailable or target invalid.")
                    input("  Enter to continue...")
            else:
                print("  Usage: potion <potion_index> [target_index]")
                input("  Enter to continue...")
        else:
            print("  Unknown command.")
            input("  Enter to continue...")

    print_combat(session, game)
    if session.player.is_dead():
        print("\n  ★ DEFEAT — the hero has fallen.\n")
        input("Enter to continue...")
        return False
    else:
        print("\n  ★ VICTORY!\n")
        input("Enter to continue...")
        return True


def run_reward(session: Session):
    clr()
    print("=== REWARD: Choose a card to add to your deck ===\n")
    for i, cid in enumerate(session.reward_choices):
        card = db.get_card(cid)
        label = str(card) if card else cid
        print(f"  [{i}] {label}")
    print("  [s] Skip")
    choice = input("\nChoose: ").strip().lower()
    if choice.isdigit() and 0 <= int(choice) < len(session.reward_choices):
        picked = session.reward_choices[int(choice)]
        session.choose_reward(picked)
        print(f"  Added {picked} to deck!")
    else:
        session.choose_reward(None)
    if session.reward_relic:
        relic = RELICS_DB[session.reward_relic]
        session.claim_relic_reward()
        print(f"  Collected relic: {relic['name']} - {relic['description']}")
    input("Enter to continue...")


def run_shop(session: Session):
    while True:
        clr()
        print(f"=== SHOP  (Gold: {session.gold}g) ===\n")
        for offer in session.shop_cards:
            card_id = offer["card_id"]
            card = db.get_card(card_id)
            label = str(card) if card else card_id
            print(f"  [{card_id}] {label}  —  {offer['price']}g")
        print("\n  Potions:")
        for offer in session.shop_potions:
            potion = POTIONS_DB[offer["potion_id"]]
            print(f"  [potion {potion['id']}] {potion['name']} - {potion['description']}  —  {offer['price']}g")
        if not session.shop_remove_used:
            print(f"\n  [remove <index>] Remove a card — 75g")
            for i, card_id in enumerate(session.master_deck):
                card = db.get_card(card_id)
                print(f"    [{i}] {card if card else card_id}")
        print("  [leave] Leave shop")
        choice = input("\nAction: ").strip().lower()
        if choice == "leave":
            break
        if choice.startswith("remove "):
            parts = choice.split()
            removed = len(parts) == 2 and parts[1].isdigit() and session.remove_card(int(parts[1]))
            print("  Removed card!" if removed else "  Card removal unavailable.")
        elif choice.startswith("potion "):
            parts = choice.split()
            bought = len(parts) == 2 and session.buy_potion(parts[1])
            print("  Bought potion!" if bought else "  Potion unavailable, inventory full, or not enough gold.")
        elif session.buy_card(choice):
            print(f"  Bought {choice}! Gold remaining: {session.gold}g")
        else:
            print("  Card unavailable or not enough gold.")
        input("Enter to continue...")
    session.leave_shop()

def run_event(session: Session):
    clr()
    event = EVENTS_DB[session.current_event]
    print(f"=== EVENT: {event['name']} ===\n")
    print(f"  {event['description']}\n")
    for choice in event["choices"]:
        print(f"  [{choice['id']}] {choice['label']} - {choice['description']}")
    while True:
        choice = input("\nChoose: ").strip().lower()
        if session.complete_event(choice):
            return
        print("  Invalid event choice.")

def run_rest(session: Session):
    clr()
    print("=== REST SITE ===\n")
    print("  [heal] Recover 30% max HP")
    print("  [upgrade <index>] Upgrade a card\n")
    for i, card_id in enumerate(session.master_deck):
        card = db.get_card(card_id)
        print(f"  [{i}] {card if card else card_id}")
    while True:
        choice = input("\nAction: ").strip().lower()
        if choice == "heal" and session.complete_rest("heal"):
            return
        if choice.startswith("upgrade "):
            parts = choice.split()
            if len(parts) == 2 and parts[1].isdigit() and session.complete_rest("upgrade", int(parts[1]), db.can_upgrade):
                return
        print("  Invalid rest action.")


def main():
    char_id = select_character()
    char = get_character(char_id)

    player = Player(char["name"], char["max_hp"], char["max_energy"])
    session = Session(player, character_id=char_id)

    while True:
        clr()
        print_map(session)

        if session.phase == "GAME_OVER":
            if session.player.is_dead():
                print("\n  ★ DEFEAT — run over.")
            else:
                print("\n  ★ RUN COMPLETE — you beat the boss!")
            input("Enter to quit...")
            break

        avail = [n for n in session.map_nodes if n.id in session.available_node_ids and not n.completed]
        if not avail:
            print("\n  No nodes available. Run complete!")
            input("Enter to quit...")
            break

        print("\nActions: go <node_id>  |  quit")
        cmd = input("> ").strip().lower()
        if cmd == "quit":
            break
        elif cmd.startswith("go "):
            parts = cmd.split()
            if len(parts) == 2 and parts[1].isdigit():
                nid = int(parts[1])
                node = session.choose_node(nid)
                if not node:
                    print("  Invalid node.")
                    input("Enter...")
                    continue
                if node.type in ("Enemy", "Elite", "Boss"):
                    victory = run_combat(session, node)
                    if not victory:
                        session.end_combat(False)
                        continue
                    session.end_combat(True)
                    if session.phase == "REWARD":
                        run_reward(session)
                elif node.type == "Shop":
                    run_shop(session)
                elif node.type == "Rest":
                    run_rest(session)
                elif node.type == "Event":
                    run_event(session)
            else:
                print("  Usage: go <node_id>")
                input("Enter...")
        else:
            print("  Unknown command.")
            input("Enter...")


if __name__ == "__main__":
    main()
