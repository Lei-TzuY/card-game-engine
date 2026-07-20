# Card Game Engine

A small deck-building card game prototype with a Flask API and static browser UI.

## Development

```powershell
python -m pip install -r requirements.txt
python server.py
```

The development server binds to `127.0.0.1:5000` by default. It uses a development secret if `CARD_GAME_SECRET_KEY` is not set.

## Tests

```powershell
python -m unittest discover -v
python -m compileall -q .
node --check static\app.js
```

## Content

Content data schemas and validation rules are documented in [docs/content_schema.md](docs/content_schema.md).

## Production

Set a real secret before using the WSGI entrypoint. The value must be non-default and at least 32 characters.

```powershell
$env:CARD_GAME_SECRET_KEY = (python -c "import secrets; print(secrets.token_urlsafe(32))")
waitress-serve --listen=0.0.0.0:5000 wsgi:application
```

The WSGI entrypoint calls `validate_app_config(require_secret=True)` and will refuse to boot with the development secret.

## Configuration

- `CARD_GAME_SECRET_KEY`: Flask session signing secret.
- `CARD_GAME_HOST`: host used by `python server.py`; default `127.0.0.1`.
- `CARD_GAME_PORT`: port used by `python server.py`; default `5000`.
- `CARD_GAME_DEBUG`: enables Flask debug mode for `python server.py`; default `false`.
- `CARD_GAME_LOG_LEVEL`: Python logging level; default `INFO`.
- `CARD_GAME_RUN_TTL_SECONDS`: TTL for temporary UUID runs; default `604800`.
- `CARD_GAME_RUN_CLEANUP_INTERVAL_SECONDS`: minimum interval between cleanup scans; default `300`.
- `CARD_GAME_RUN_LOCK_TIMEOUT_SECONDS`: timeout while waiting for a run lock; default `5`.
- `CARD_GAME_RUN_LOCK_STALE_SECONDS`: stale lock age before automatic recovery; default `30`.

Run state is stored under `data/runs`. Fixed save slots use `slot_1`, `slot_2`, and `slot_3`; temporary browser runs use UUID filenames.

## Ascension

Each run can be started at an Ascension difficulty level (0–5), selected per character on the character-select screen. Levels are cumulative and add modifiers: tougher enemies, tougher elites/bosses, reduced starting HP, weaker rests, and less starting gold.

Higher levels unlock by winning a run at the level below. Unlock progress is persisted per character in `data/meta.json` (separate from run saves, so it survives run resets). `GET /api/meta` returns the level definitions and per-character unlock state.
