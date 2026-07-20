import os
import tempfile
import threading
import time
import unittest
import uuid
from unittest.mock import patch

import server
from engine.entities import Enemy, Player
from engine.game import Game
from engine.session import MapNode, Session


def enemy_data(name="Slime", hp=10, attack=5):
    return {
        "name": name,
        "hp": hp,
        "attack": attack,
        "actions": [{"type": "attack", "amount": attack}],
        "phases": [],
        "passives": [],
    }


class ServerTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        server.SAVE_DIR = self.temp_dir.name
        server.runs.clear()
        server._last_cleanup_at = 0.0
        self.lock_config = (server.RUN_LOCK_TIMEOUT_SECONDS, server.RUN_LOCK_STALE_SECONDS)
        self.secret_key = server.app.secret_key
        self.client = server.app.test_client()
        self.run_id = uuid.uuid4().hex

    def tearDown(self):
        server.runs.clear()
        server._last_cleanup_at = 0.0
        server.RUN_LOCK_TIMEOUT_SECONDS, server.RUN_LOCK_STALE_SECONDS = self.lock_config
        server.app.secret_key = self.secret_key
        self.temp_dir.cleanup()

    def bind_run(self, session, game=None):
        return server.bind_test_run(self.client, session, game, self.run_id)

    @property
    def save_file(self):
        return server.save_filepath(self.run_id)


class ServerShopTests(ServerTestCase):
    def setUp(self):
        super().setUp()
        self.session = Session(Player("Hero", 50))
        self.shop = MapNode(1, "Shop", [], floor=1)
        self.enemy = MapNode(2, "Enemy", [enemy_data()], floor=2)
        self.shop.connections = [self.enemy.id]
        self.session.map_nodes = [self.shop, self.enemy]
        self.session.available_node_ids = [self.shop.id]
        self.run = self.bind_run(self.session)

    def test_shop_node_does_not_start_combat(self):
        response = self.client.post("/api/choose_node", json={"node_id": 1})
        state = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(state["session"]["phase"], "SHOP")
        self.assertNotIn("game", state)
        self.assertIsNone(self.run.game)

    def test_buy_and_leave_shop(self):
        self.client.post("/api/choose_node", json={"node_id": 1})
        card_id = self.session.shop_cards[0]["card_id"]

        buy_response = self.client.post("/api/shop/buy", json={"card_id": card_id})
        leave_response = self.client.post("/api/shop/leave")
        state = leave_response.get_json()

        self.assertEqual(buy_response.status_code, 200)
        self.assertEqual(leave_response.status_code, 200)
        self.assertIn(card_id, self.session.master_deck)
        self.assertEqual(state["session"]["phase"], "MAP")
        self.assertEqual(state["session"]["available_node_ids"], [2])

    def test_buy_rejects_unlisted_card(self):
        self.client.post("/api/choose_node", json={"node_id": 1})

        response = self.client.post("/api/shop/buy", json={"card_id": "not-offered"})

        self.assertEqual(response.status_code, 400)

    def test_restart_requires_character_selection(self):
        with open(self.save_file, "w", encoding="utf-8") as save_file:
            save_file.write("{}")
        with open(Session.backup_filepath(self.save_file), "w", encoding="utf-8") as backup_file:
            backup_file.write("{}")
        with open(Session.temp_filepath(self.save_file), "w", encoding="utf-8") as temp_file:
            temp_file.write("{}")

        response = self.client.post("/api/restart")
        state = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(state["session"]["phase"], "CHARACTER_SELECT")
        self.assertIsNone(state["session"]["player"])
        self.assertIn("pommel_strike", state["cards"])
        self.assertEqual(len(state["characters"]), 5)
        self.assertFalse(os.path.exists(self.save_file))
        self.assertFalse(os.path.exists(Session.backup_filepath(self.save_file)))
        self.assertFalse(os.path.exists(Session.temp_filepath(self.save_file)))

        response = self.client.post("/api/start_run", json={"character_id": "silent"})
        state = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(state["session"]["phase"], "MAP")
        self.assertEqual(state["session"]["character_id"], "silent")
        self.assertEqual(state["session"]["player"]["max_hp"], 70)

    def test_start_run_rejects_invalid_character(self):
        self.client.post("/api/restart")

        response = self.client.post("/api/start_run", json={"character_id": "unknown"})

        self.assertEqual(response.status_code, 400)

    def test_shop_remove_endpoint_charges_gold_once(self):
        self.client.post("/api/choose_node", json={"node_id": 1})
        self.session.gold = 100
        starting_size = len(self.session.master_deck)

        response = self.client.post("/api/shop/remove", json={"card_index": 0})
        repeat = self.client.post("/api/shop/remove", json={"card_index": 0})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(repeat.status_code, 400)
        self.assertEqual(self.session.gold, 25)
        self.assertEqual(len(self.session.master_deck), starting_size - 1)

    def test_shop_potion_endpoint_charges_gold_and_fills_slot(self):
        self.client.post("/api/choose_node", json={"node_id": 1})
        potion_id = self.session.shop_potions[0]["potion_id"]
        self.session.gold = 40

        response = self.client.post("/api/shop/potion", json={"potion_id": potion_id})
        state = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(state["session"]["gold"], 0)
        self.assertIn(potion_id, [potion["id"] for potion in state["session"]["potions"]])


class ServerCombatNodeTests(ServerTestCase):
    def setUp(self):
        super().setUp()
        self.session = Session(Player("Hero", 50))
        self.enemy = MapNode(
            1,
            "Enemy",
            [
                {
                    "name": "Mad Gremlin",
                    "hp": 20,
                    "attack": 4,
                    "actions": [{"type": "attack", "amount": 4}, {"type": "strength", "amount": 1}],
                    "phases": [],
                    "passives": ["Enrage"],
                }
            ],
            floor=1,
        )
        self.session.map_nodes = [self.enemy]
        self.session.available_node_ids = [self.enemy.id]
        self.run = self.bind_run(self.session)

    def test_choose_combat_node_preserves_enemy_passives(self):
        response = self.client.post("/api/choose_node", json={"node_id": 1})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.run.game.enemies[0].passives, ["Enrage"])


class ServerRestTests(ServerTestCase):
    def setUp(self):
        super().setUp()
        self.session = Session(Player("Hero", 50))
        self.rest = MapNode(1, "Rest", [], floor=1)
        self.enemy = MapNode(2, "Enemy", [enemy_data()], floor=2)
        self.rest.connections = [self.enemy.id]
        self.session.map_nodes = [self.rest, self.enemy]
        self.session.available_node_ids = [self.rest.id]
        self.bind_run(self.session)

    def test_rest_upgrade_endpoint_advances_map(self):
        self.client.post("/api/choose_node", json={"node_id": 1})

        response = self.client.post("/api/rest", json={"action": "upgrade", "card_index": 0})
        state = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(state["session"]["phase"], "MAP")
        self.assertEqual(state["session"]["master_deck"][0], "strike+")
        self.assertEqual(state["session"]["available_node_ids"], [2])


class ServerRewardAndPotionTests(ServerTestCase):
    def setUp(self):
        super().setUp()
        self.session = Session(Player("Hero", 50))
        self.run = self.bind_run(self.session)

    def test_claim_relic_reward_endpoint_finishes_reward(self):
        self.session.phase = "REWARD"
        self.session.reward_relic = "vajra"
        self.session.reward_card_resolved = True

        response = self.client.post("/api/reward/relic")
        state = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(state["session"]["phase"], "MAP")
        self.assertIn("Vajra", [relic["name"] for relic in state["session"]["relics"]])

    def test_use_fire_potion_endpoint_consumes_potion(self):
        self.session.phase = "COMBAT"
        self.session.potions = ["fire_potion"]
        self.run.game = Game(self.session.player, [Enemy("Slime", 30)], server.db)

        response = self.client.post("/api/potion/use", json={"potion_index": 0})
        state = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(state["game"]["enemies"][0]["hp"], 10)
        self.assertEqual(state["session"]["potions"], [])


class ServerEventTests(ServerTestCase):
    def setUp(self):
        super().setUp()
        self.session = Session(Player("Hero", 50))
        self.event = MapNode(1, "Event", [], floor=1)
        self.next_node = MapNode(2, "Enemy", [enemy_data()], floor=2)
        self.event.connections = [self.next_node.id]
        self.session.map_nodes = [self.event, self.next_node]
        self.session.available_node_ids = [self.event.id]
        self.bind_run(self.session)

    def test_event_choice_endpoint_advances_map(self):
        with patch("engine.session.random.choice", return_value="golden_idol"):
            open_response = self.client.post("/api/choose_node", json={"node_id": 1})
        self.assertEqual(open_response.get_json()["session"]["phase"], "EVENT")

        starting_gold = self.session.gold
        response = self.client.post("/api/event", json={"choice_id": "take"})
        state = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(state["session"]["phase"], "MAP")
        self.assertEqual(state["session"]["gold"], starting_gold + 100)
        self.assertEqual(state["session"]["player"]["hp"], 43)
        self.assertEqual(state["session"]["available_node_ids"], [2])


class ServerCombatResumeTests(ServerTestCase):
    def setUp(self):
        super().setUp()
        self.session = Session(Player("Hero", 50))
        self.session.phase = "COMBAT"
        self.game = Game(self.session.player, [Enemy("Slime", 30)], server.db)
        self.game.hand.add(server.db.get_card("strike"))
        self.bind_run(self.session, self.game)

    def test_play_autosaves_and_memory_reset_restores_same_combat(self):
        response = self.client.post("/api/play", json={"index": 0})
        state = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(state["game"]["enemies"][0]["hp"], 24)

        server.runs.clear()
        restored = self.client.get("/api/state").get_json()

        self.assertEqual(restored["session"]["phase"], "COMBAT")
        self.assertEqual(restored["session"]["player"]["energy"], 2)
        self.assertEqual(restored["game"]["enemies"][0]["hp"], 24)
        self.assertEqual(restored["game"]["hand"], [])
        self.assertEqual(restored["game"]["discard_size"], 1)

    def test_request_recovers_backup_when_primary_save_is_corrupt(self):
        session = Session(Player("Hero", 50))
        session.save_to_file(self.save_file)
        session.player.hp = 35
        session.save_to_file(self.save_file)
        with open(self.save_file, "w", encoding="utf-8") as save_file:
            save_file.write("{bad json")

        server.runs.clear()
        restored = self.client.get("/api/state").get_json()

        self.assertEqual(restored["session"]["player"]["hp"], 50)
        self.assertEqual(restored["session"]["phase"], "MAP")
        invalid_files = [name for name in os.listdir(self.temp_dir.name) if ".invalid-" in name]
        self.assertEqual(len(invalid_files), 1)


class ServerIsolationTests(ServerTestCase):
    def test_two_clients_keep_independent_runs_and_save_files(self):
        second_client = server.app.test_client()

        first = self.client.post("/api/start_run", json={"character_id": "silent"}).get_json()
        second = second_client.post("/api/start_run", json={"character_id": "defect"}).get_json()

        self.assertEqual(first["session"]["character_id"], "silent")
        self.assertEqual(second["session"]["character_id"], "defect")
        first_state = self.client.get("/api/state").get_json()
        second_state = second_client.get("/api/state").get_json()
        self.assertEqual(first_state["session"]["player"]["max_hp"], 70)
        self.assertEqual(second_state["session"]["player"]["max_hp"], 75)
        save_files = [name for name in os.listdir(self.temp_dir.name) if name.endswith(".json")]
        self.assertEqual(len(save_files), 2)

    def test_restart_only_clears_current_clients_run(self):
        second_client = server.app.test_client()
        self.client.post("/api/start_run", json={"character_id": "silent"})
        second_client.post("/api/start_run", json={"character_id": "defect"})

        reset_state = self.client.post("/api/restart").get_json()
        second_state = second_client.get("/api/state").get_json()

        self.assertEqual(reset_state["session"]["phase"], "CHARACTER_SELECT")
        self.assertEqual(second_state["session"]["character_id"], "defect")
        self.assertEqual(second_state["session"]["phase"], "MAP")


class ServerRunStoreTests(ServerTestCase):
    def test_health_endpoint_reports_ok_without_sensitive_config(self):
        response = self.client.get("/api/health")
        state = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(state["status"], "ok")
        self.assertEqual(state["slots"], ["slot_1", "slot_2", "slot_3"])
        self.assertIn("runs_in_memory", state)
        self.assertIn("secret_configured", state)
        self.assertNotIn("secret", state)

    def test_validate_app_config_requires_production_secret(self):
        server.app.secret_key = server.DEV_SECRET_KEY
        with self.assertRaises(RuntimeError):
            server.validate_app_config(require_secret=True)

        server.app.secret_key = "x" * 31
        with self.assertRaises(RuntimeError):
            server.validate_app_config(require_secret=True)

        server.app.secret_key = "x" * 32
        server.validate_app_config(require_secret=True)

    def test_api_not_found_returns_json_error(self):
        response = self.client.get("/api/does_not_exist")
        state = response.get_json()

        self.assertEqual(response.status_code, 404)
        self.assertIn("error", state)

    def test_file_lock_timeout_returns_409(self):
        server.RUN_LOCK_TIMEOUT_SECONDS = 0.05
        self.bind_run(Session(Player("Hero", 50)))

        with server.RunFileLock(self.run_id, timeout_seconds=0.5):
            response = self.client.get("/api/state")

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.get_json()["error"], "Run is busy. Please retry.")

    def test_stale_lock_file_is_recovered(self):
        lock_file = server.lock_filepath(self.run_id)
        os.makedirs(self.temp_dir.name, exist_ok=True)
        with open(lock_file, "w", encoding="utf-8") as stale_lock:
            stale_lock.write("stale")
        stale_time = time.time() - 10
        os.utime(lock_file, (stale_time, stale_time))

        with server.RunFileLock(self.run_id, timeout_seconds=0.2, stale_seconds=0.01):
            self.assertTrue(os.path.exists(lock_file))

        self.assertFalse(os.path.exists(lock_file))

    def test_request_refreshes_newer_storage_before_responding(self):
        self.bind_run(Session(Player("Hero", 50)))
        external_session = Session(Player("Hero", 50))
        external_session.player.hp = 31
        external_session.save_to_file(self.save_file)

        state = self.client.get("/api/state").get_json()

        self.assertEqual(state["session"]["player"]["hp"], 31)
        self.assertEqual(server.runs[self.run_id].session.player.hp, 31)

    def test_loaded_slot_remains_bound_for_follow_up_requests(self):
        response = self.client.post("/api/load_slot", json={"slot_id": "slot_1"})
        self.assertEqual(response.status_code, 200)

        start_response = self.client.post("/api/start_run", json={"character_id": "silent"})
        start_state = start_response.get_json()
        self.assertEqual(start_response.status_code, 200)
        self.assertEqual(start_state["session"]["character_id"], "silent")
        self.assertTrue(os.path.exists(server.save_filepath("slot_1")))

        server.runs.clear()
        restored = self.client.get("/api/state").get_json()

        self.assertEqual(restored["session"]["character_id"], "silent")
        self.assertEqual(restored["session"]["phase"], "MAP")

    def test_delete_slot_removes_save_family(self):
        session = Session(Player("Hero", 50))
        save_file = server.save_filepath("slot_2")
        session.save_to_file(save_file)
        session.player.hp = 35
        session.save_to_file(save_file)
        temp_file = Session.temp_filepath(save_file)
        invalid_file = f"{save_file}.invalid-20260603T000000Z"
        with open(temp_file, "w", encoding="utf-8") as temp_save:
            temp_save.write("{}")
        with open(invalid_file, "w", encoding="utf-8") as isolated_save:
            isolated_save.write("{}")

        response = self.client.post("/api/delete_slot", json={"slot_id": "slot_2"})

        self.assertEqual(response.status_code, 200)
        self.assertFalse(os.path.exists(save_file))
        self.assertFalse(os.path.exists(Session.backup_filepath(save_file)))
        self.assertFalse(os.path.exists(temp_file))
        self.assertFalse(os.path.exists(invalid_file))

    def test_cleanup_preserves_stale_slot_save_files(self):
        now = time.time()
        stale_time = now - server.RUN_TTL_SECONDS - 1
        slot_run = server.RunState(Session(Player("Hero", 50)))
        slot_run.last_access = stale_time
        server.runs["slot_3"] = slot_run
        save_file = server.save_filepath("slot_3")
        slot_run.session.save_to_file(save_file)
        os.utime(save_file, (stale_time, stale_time))

        removed = server.cleanup_stale_runs(now=now, force=True)

        self.assertIn("slot_3", removed)
        self.assertNotIn("slot_3", server.runs)
        self.assertTrue(os.path.exists(save_file))

    def test_same_run_requests_are_serialized(self):
        second_client = server.app.test_client()
        session = Session(Player("Hero", 50))
        session.phase = "SHOP"
        self.bind_run(session)
        with second_client.session_transaction() as cookie:
            cookie["run_id"] = self.run_id

        counter_lock = threading.Lock()
        first_entered = threading.Event()
        second_entered = threading.Event()
        release_first = threading.Event()
        active_count = 0
        call_count = 0
        max_active_count = 0

        def slow_leave_shop():
            nonlocal active_count, call_count, max_active_count
            with counter_lock:
                active_count += 1
                call_count += 1
                current_call = call_count
                max_active_count = max(max_active_count, active_count)
            if current_call == 1:
                first_entered.set()
                release_first.wait(timeout=2)
            else:
                second_entered.set()
            time.sleep(0.02)
            with counter_lock:
                active_count -= 1
            return True

        session.leave_shop = slow_leave_shop
        responses = {}
        first_thread = threading.Thread(
            target=lambda: responses.setdefault("first", self.client.post("/api/shop/leave").status_code)
        )
        second_thread = threading.Thread(
            target=lambda: responses.setdefault("second", second_client.post("/api/shop/leave").status_code)
        )
        first_thread.start()
        second_started = False
        try:
            self.assertTrue(first_entered.wait(timeout=1))
            second_thread.start()
            second_started = True
            self.assertFalse(second_entered.wait(timeout=0.1))
        finally:
            release_first.set()
            first_thread.join(timeout=2)
            if second_started:
                second_thread.join(timeout=2)

        self.assertFalse(first_thread.is_alive())
        self.assertFalse(second_thread.is_alive())
        self.assertEqual(responses, {"first": 200, "second": 200})
        self.assertEqual(max_active_count, 1)

    def test_cleanup_removes_stale_memory_run_and_its_save_family(self):
        now = time.time()
        stale_time = now - server.RUN_TTL_SECONDS - 1
        stale_run_id = uuid.uuid4().hex
        stale_run = server.RunState(Session(Player("Hero", 50)))
        stale_run.last_access = stale_time
        server.runs[stale_run_id] = stale_run
        save_file = server.save_filepath(stale_run_id)
        stale_run.session.save_to_file(save_file)
        stale_run.session.save_to_file(save_file)
        invalid_file = f"{save_file}.invalid-20260603T000000Z"
        backup_temp_file = f"{save_file}.bak.tmp"
        with open(invalid_file, "w", encoding="utf-8") as isolated_save:
            isolated_save.write("{}")
        with open(backup_temp_file, "w", encoding="utf-8") as backup_temp:
            backup_temp.write("{}")
        for name in os.listdir(self.temp_dir.name):
            os.utime(os.path.join(self.temp_dir.name, name), (stale_time, stale_time))

        removed = server.cleanup_stale_runs(now=now, force=True)

        self.assertIn(stale_run_id, removed)
        self.assertNotIn(stale_run_id, server.runs)
        self.assertEqual(os.listdir(self.temp_dir.name), [])

    def test_cleanup_removes_stale_orphan_but_preserves_fresh_and_unrelated_files(self):
        now = time.time()
        stale_time = now - server.RUN_TTL_SECONDS - 1
        stale_run_id = uuid.uuid4().hex
        fresh_run_id = uuid.uuid4().hex
        stale_file = server.save_filepath(stale_run_id)
        fresh_file = server.save_filepath(fresh_run_id)
        unrelated_file = os.path.join(self.temp_dir.name, "notes.json")
        with open(stale_file, "w", encoding="utf-8") as save_file:
            save_file.write("{}")
        with open(fresh_file, "w", encoding="utf-8") as save_file:
            save_file.write("{}")
        with open(unrelated_file, "w", encoding="utf-8") as notes:
            notes.write("{}")
        os.utime(stale_file, (stale_time, stale_time))

        removed = server.cleanup_stale_runs(now=now, force=True)

        self.assertIn(stale_run_id, removed)
        self.assertFalse(os.path.exists(stale_file))
        self.assertTrue(os.path.exists(fresh_file))
        self.assertTrue(os.path.exists(unrelated_file))

    def test_cleanup_skips_stale_run_while_request_lock_is_held(self):
        now = time.time()
        stale_time = now - server.RUN_TTL_SECONDS - 1
        stale_run_id = uuid.uuid4().hex
        stale_run = server.RunState(Session(Player("Hero", 50)))
        stale_run.last_access = stale_time
        server.runs[stale_run_id] = stale_run
        save_file = server.save_filepath(stale_run_id)
        stale_run.session.save_to_file(save_file)
        os.utime(save_file, (stale_time, stale_time))
        lock_acquired = threading.Event()
        release_lock = threading.Event()

        def hold_request_lock():
            with stale_run.lock:
                lock_acquired.set()
                release_lock.wait(timeout=2)

        holder = threading.Thread(target=hold_request_lock)
        holder.start()
        try:
            self.assertTrue(lock_acquired.wait(timeout=1))
            removed = server.cleanup_stale_runs(now=now, force=True)
        finally:
            release_lock.set()
            holder.join(timeout=2)

        self.assertNotIn(stale_run_id, removed)
        self.assertIn(stale_run_id, server.runs)
        self.assertTrue(os.path.exists(save_file))


if __name__ == "__main__":
    unittest.main()
