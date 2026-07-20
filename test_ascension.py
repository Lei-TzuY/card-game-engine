import os
import tempfile
import unittest
from unittest.mock import patch

import server
from engine import meta as meta_module
from engine.ascension import (
    MAX_ASCENSION,
    ascension_levels,
    clamp_ascension,
    enemy_hp_multiplier,
    rest_heal_fraction,
    scale_enemy_hp,
    starting_gold,
    starting_hp_fraction,
)
from engine.entities import Player
from engine.meta import (
    HISTORY_CAP,
    get_history,
    is_ascension_allowed,
    load_meta,
    max_unlocked,
    record_run,
    record_victory,
    save_meta,
)
from engine.session import Session, _make_enemy


class AscensionMathTests(unittest.TestCase):
    def test_clamp_rejects_out_of_range_and_bools(self):
        self.assertEqual(clamp_ascension(-3), 0)
        self.assertEqual(clamp_ascension(99), MAX_ASCENSION)
        self.assertEqual(clamp_ascension(True), 0)
        self.assertEqual(clamp_ascension("2"), 0)

    def test_enemy_hp_scaling_is_cumulative_and_tiered(self):
        self.assertEqual(scale_enemy_hp(100, 0, "normal"), 100)
        self.assertEqual(scale_enemy_hp(100, 1, "normal"), 110)
        # Normal enemies do not get the level-2 elite/boss bonus.
        self.assertEqual(scale_enemy_hp(100, 2, "normal"), 110)
        # Bosses stack both multipliers: 1.10 * 1.10 = 1.21.
        self.assertEqual(scale_enemy_hp(100, 2, "boss"), 121)
        self.assertAlmostEqual(enemy_hp_multiplier(2, "elite"), 1.21)

    def test_run_start_modifiers_kick_in_at_thresholds(self):
        self.assertEqual(starting_gold(0), 99)
        self.assertEqual(starting_gold(5), 74)
        self.assertEqual(starting_hp_fraction(2), 1.0)
        self.assertEqual(starting_hp_fraction(3), 0.90)
        self.assertEqual(rest_heal_fraction(3), 0.30)
        self.assertEqual(rest_heal_fraction(4), 0.25)

    def test_levels_cover_zero_through_max(self):
        levels = ascension_levels()
        self.assertEqual(levels[0]["level"], 0)
        self.assertEqual(levels[0]["effects"], [])
        self.assertEqual(levels[-1]["level"], MAX_ASCENSION)
        self.assertEqual(len(levels[-1]["effects"]), MAX_ASCENSION)

    def test_make_enemy_scales_hp_by_ascension(self):
        entry = ["Test Brute", 100, [{"type": "attack", "amount": 5}]]
        with patch("engine.session.random.choice", return_value=entry):
            self.assertEqual(_make_enemy("normal", 0)["hp"], 100)
            self.assertEqual(_make_enemy("normal", 1)["hp"], 110)


class MetaProgressionTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.temp_dir.name, "meta.json")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_missing_meta_defaults_to_zero(self):
        meta = load_meta(self.path)
        self.assertEqual(max_unlocked(meta, "ironclad"), 0)

    def test_record_victory_unlocks_next_level_and_persists(self):
        meta = load_meta(self.path)
        self.assertTrue(record_victory(meta, "ironclad", 0))
        self.assertEqual(max_unlocked(meta, "ironclad"), 1)
        # Re-winning at an already-cleared level does not change anything.
        self.assertFalse(record_victory(meta, "ironclad", 0))
        save_meta(meta, self.path)
        self.assertEqual(max_unlocked(load_meta(self.path), "ironclad"), 1)

    def test_allowed_levels_respect_unlock_and_character(self):
        meta = load_meta(self.path)
        record_victory(meta, "silent", 0)
        self.assertTrue(is_ascension_allowed(meta, "silent", 1))
        self.assertFalse(is_ascension_allowed(meta, "silent", 2))
        self.assertFalse(is_ascension_allowed(meta, "ironclad", 1))

    def test_record_victory_caps_at_max(self):
        meta = load_meta(self.path)
        record_victory(meta, "defect", MAX_ASCENSION)
        self.assertEqual(max_unlocked(meta, "defect"), MAX_ASCENSION)

    def test_record_run_prepends_and_caps_history(self):
        meta = load_meta(self.path)
        for i in range(HISTORY_CAP + 5):
            record_run(meta, {"character": "ironclad", "score": i})
        history = get_history(meta)
        self.assertEqual(len(history), HISTORY_CAP)
        # Most recent run is first.
        self.assertEqual(history[0]["score"], HISTORY_CAP + 4)

    def test_history_survives_save_and_load(self):
        meta = load_meta(self.path)
        record_run(meta, {"character": "silent", "ascension": 1, "floor": 7, "won": True,
                          "gold": 40, "score": 333, "timestamp": "2026-06-29T00:00:00+00:00"})
        save_meta(meta, self.path)
        reloaded = get_history(load_meta(self.path))
        self.assertEqual(len(reloaded), 1)
        self.assertEqual(reloaded[0]["score"], 333)

    def test_corrupt_history_entries_are_dropped_on_load(self):
        save_meta({"history": ["nonsense", {"no_score": 1}, {"score": 10}]}, self.path)
        history = get_history(load_meta(self.path))
        self.assertEqual([entry["score"] for entry in history], [10])

    def test_corrupt_meta_falls_back_to_empty(self):
        with open(self.path, "w", encoding="utf-8") as f:
            f.write("not json {")
        meta = load_meta(self.path)
        self.assertEqual(max_unlocked(meta, "ironclad"), 0)


class SessionAscensionTests(unittest.TestCase):
    def test_session_uses_ascension_starting_gold(self):
        session = Session(Player("Hero", 80), character_id="ironclad", ascension=5)
        self.assertEqual(session.ascension, 5)
        self.assertEqual(session.gold, 74)

    def test_ascension_round_trips_through_save(self):
        session = Session(Player("Hero", 80), character_id="ironclad", ascension=3)
        restored = Session._from_save_data(session.to_dict())
        self.assertEqual(restored.ascension, 3)

    def test_rest_heal_scales_with_ascension(self):
        session = Session(Player("Hero", 100), character_id="ironclad", ascension=4)
        session.player.hp = 1
        session.phase = "REST"
        session.current_node_id = session.map_nodes[0].id
        session.complete_rest("heal")
        self.assertEqual(session.player.hp, 1 + 25)  # 25% of 100 at A4

    def test_compute_score_rewards_progress_and_victory(self):
        session = Session(Player("Hero", 80), character_id="ironclad", ascension=2)
        session.floor = 8
        session.gold = 50
        session.run_won = True
        # floor*10 + ascension*30 + gold//5 + 250 win bonus
        self.assertEqual(session.compute_score(), 80 + 60 + 10 + 250)

    def test_run_summary_has_expected_fields(self):
        session = Session(Player("Hero", 80), character_id="silent", ascension=1)
        summary = session.run_summary()
        for field in ("character", "ascension", "floor", "won", "gold", "score", "timestamp"):
            self.assertIn(field, summary)
        self.assertEqual(summary["character"], "silent")


class ServerAscensionTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        server.SAVE_DIR = self.temp_dir.name
        server.runs.clear()
        server._last_cleanup_at = 0.0
        self.meta_path = os.path.join(self.temp_dir.name, "meta.json")
        self._load_meta, self._save_meta = server.load_meta, server.save_meta
        server.load_meta = lambda *a, **k: meta_module.load_meta(self.meta_path)
        server.save_meta = lambda meta, *a, **k: meta_module.save_meta(meta, self.meta_path)
        self.client = server.app.test_client()

    def tearDown(self):
        server.load_meta, server.save_meta = self._load_meta, self._save_meta
        server.runs.clear()
        server._last_cleanup_at = 0.0
        self.temp_dir.cleanup()

    def test_meta_endpoint_lists_all_levels(self):
        body = self.client.get("/api/meta").get_json()
        self.assertEqual(body["max_ascension"], MAX_ASCENSION)
        self.assertEqual(len(body["levels"]), MAX_ASCENSION + 1)

    def test_start_run_rejects_locked_ascension(self):
        response = self.client.post("/api/start_run", json={"character_id": "ironclad", "ascension": 1})
        self.assertEqual(response.status_code, 400)

    def test_start_run_allows_unlocked_ascension_and_applies_hp_penalty(self):
        seed = meta_module.load_meta(self.meta_path)
        seed.setdefault("ascension_unlocked", {})["ironclad"] = 3
        meta_module.save_meta(seed, self.meta_path)

        response = self.client.post("/api/start_run", json={"character_id": "ironclad", "ascension": 3})
        self.assertEqual(response.status_code, 200)
        session = response.get_json()["session"]
        self.assertEqual(session["ascension"], 3)
        self.assertEqual(session["player"]["hp"], int(session["player"]["max_hp"] * 0.9))

    def test_victory_unlocks_next_level(self):
        session = Session(Player("Hero", 80), character_id="ironclad", ascension=0)
        session.run_won = True
        session.phase = "GAME_OVER"
        server.finalize_if_run_over(session)
        self.assertEqual(max_unlocked(meta_module.load_meta(self.meta_path), "ironclad"), 1)

    def test_dead_player_does_not_unlock(self):
        session = Session(Player("Hero", 80), character_id="silent", ascension=0)
        session.run_won = True
        session.player.hp = 0
        session.phase = "GAME_OVER"
        server.finalize_if_run_over(session)
        self.assertEqual(max_unlocked(meta_module.load_meta(self.meta_path), "silent"), 0)

    def test_finalize_records_history_exactly_once(self):
        session = Session(Player("Hero", 80), character_id="ironclad", ascension=0)
        session.run_won = True
        session.phase = "GAME_OVER"
        server.finalize_if_run_over(session)
        server.finalize_if_run_over(session)  # idempotent
        history = meta_module.get_history(meta_module.load_meta(self.meta_path))
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["character"], "ironclad")
        self.assertTrue(history[0]["won"])

    def test_meta_endpoint_includes_history(self):
        self.assertIn("history", self.client.get("/api/meta").get_json())


if __name__ == "__main__":
    unittest.main()
