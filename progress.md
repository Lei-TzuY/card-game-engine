# Progress

## 2026-06-18
- Created planning files for the Card Game Engine completion pass.
- Inspected project root and content-data test entry points; corrected initial assumption about nonexistent central content/model modules.
- Read session, entity, event, relic, data, and test files; selected a scoped approach that preserves the enemy JSON format while adding validation.
- Completed orientation and started enemy/map validation implementation.
- Added enemy DB validation, generated map validation, API passive preservation, and tests. Targeted test run passed: `python -m unittest test_content_data.py test_session.py test_server.py -v` (80 tests).
- Added `docs/content_schema.md` and linked it from `README.md`.
- Added 3 events, 3 implemented relics, and 7 enemy entries across easy/normal/elite/boss tiers.
- Verification passed: `python -m unittest discover -v` (127 tests), `python -m compileall -q .`, and `node --check static\app.js`.

## 2026-06-21
- Added saved-session validation on both save and load paths.
- Save validation now rejects invalid phase, floor, gold, potion capacity, unknown relics/potions/events, malformed reward/shop state, invalid available/current map node references, and malformed saved map nodes.
- Updated hand-built test map fixtures to use full runtime enemy data matching the generated map schema.
- Added invalid save regression tests for backup recovery and invalid map isolation.
- Verification passed: `python -m unittest discover -v` (129 tests), `python -m compileall -q .` with an isolated pycache prefix, `node --check static\app.js`, and live Flask API smoke test.
- Fixed static map rendering so generated map nodes expose `data-node-id` for SVG connection drawing.
- Added static UI regression tests covering static asset references, map connection DOM contract, and `node --check static\app.js`.
- Verification passed after the UI fix: `python -m unittest discover -v` (132 tests), `python -m compileall -q .`, `node --check static\app.js`, and live Flask HTTP smoke test for `/`, `/static/app.js`, `/api/health`, start run, and abandon run.
