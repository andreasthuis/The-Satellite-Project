# The Satellite Project
The Satellite Project is a reimagination of the late Roblox Satellite Project, only in Discord this time!

## Stack

- Python 3.12
- discord.py
- Redis with persistence

## Setup

1. Create a Python 3.12 virtual environment at the repository root.
2. Install dependencies with `pip install -r requirements.txt`.
3. Copy `.env.example` to `.env` and fill in your Discord bot token.
4. Start Redis locally, or run `docker compose up -d redis`.
5. Launch the bot with `python main.py`.

## Command Sync

- `COMMAND_SYNC_MODE=guild` is the default and is best for rapid hybrid-command iteration.
- Set `DEV_GUILD_ID` to your test server so slash-command updates sync there quickly.
- Use `COMMAND_SYNC_MODE=global` only when you want to publish globally.
- Use `COMMAND_SYNC_MODE=none` if you want to skip slash-command syncing entirely for a run.

## Structure

- `main.py` is a tiny launcher for local runs.
- `src/main.py` contains bot startup and lifecycle code.
- `src/commands/` holds modular command definitions.
- `src/redis_client.py` owns the shared Redis connection.

## Transparency Sidenote
This project was created with the assistance of AI. This is also my first time using a dedicated agent [Codex] for agentic coding.
Definitely a little unusual for my side, but might as well check it out, why not?
