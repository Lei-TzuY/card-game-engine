# Card Game Engine Completion Plan

## Goal
Improve the remaining content infrastructure by adding enemy/map validation, documenting content schemas, and expanding balanced enemy/event/relic content without destabilizing the existing loop or API tests.

## Phases

### Phase 1 - Project Orientation
Status: complete
- Inspect current data layout, validators, tests, and content conventions.
- Identify the narrowest validation/documentation/content changes that fit the codebase.

### Phase 2 - Enemy And Map Validation
Status: complete
- Add or extend tests for enemy and map data validation.
- Implement validation checks using existing patterns.

### Phase 3 - Schema Documentation
Status: complete
- Add content schema documentation for data authors.
- Cover characters, cards, enemies, events, potions, relics, and map structures as supported by current code.

### Phase 4 - Content Expansion
Status: complete
- Add a focused batch of balanced events, enemies, and relics.
- Keep behavior deterministic/testable and aligned with existing effects.

### Phase 5 - Verification
Status: complete
- Run the relevant test suite.
- Fix any regressions and record final status.

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| Tried to read nonexistent `engine/content.py` and `engine/models.py` | 1 | Use actual per-domain modules discovered by `rg --files`. |
| PowerShell `rg` call used `test_*.py`, which is not valid as passed to ripgrep on this shell | 1 | Use broader explicit paths or `rg --files` output instead. |
| `git status` / `git diff` failed because `Card Game Engine` is not a git repository | 1 | Use known modified-file list and test results for final summary. |
