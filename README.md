# The Satellite Project

The Satellite Project is a reimagining of the late Harbinger Satellite Roblox Project, rebuilt for Discord.

It allows Discord servers to bind a channel to a shared satellite network, so messages sent in one subscribed server can be relayed to the others.

## Open Source

Unlike the original Harbinger Satellite setup, The Satellite Project is open source.

That means you can:

- self-host your own instance
- run your own private satellite network
- inspect and modify the source
- contribute improvements back to the project

## Features

- Cross-server relay system for subscribed channels
- Bind, rebind, unbind, connect, and disconnect controls
- Optional webhook-based relays for cleaner message formatting
- Redis-backed subscription storage
- Hybrid commands with both slash and prefix support

## Tech Stack

- Python 3.12
- `discord.py`
- Redis

## Quick Start

```bash
git clone https://github.com/Encythes-Works/The-Satellite-Project.git
cd The-Satellite-Project
python -m venv .venv
pip install -r requirements.txt
python main.py
```

Before running the bot, copy [`.env.example`](/E:/Projects/Python/The-Satellite-Project/.env.example) to `.env` and fill in your values.

## Core Commands

- `$>bind` / `/bind`
- `$>rebind` / `/rebind`
- `$>unbind` / `/unbind`
- `$>connect` / `/connect`
- `$>disconnect` / `/disconnect`
- `$>network` / `/network`
- `$>ping` / `/ping`

## Command Sync

For development, use:

```env
COMMAND_SYNC_MODE=guild
DEV_GUILD_ID=your_test_server_id
```

This makes slash-command updates much faster while you iterate.

## Project Layout

- [main.py](/E:/Projects/Python/The-Satellite-Project/main.py): local entrypoint
- [src/main.py](/E:/Projects/Python/The-Satellite-Project/src/main.py): startup, sync, and relay logic
- [src/commands](/E:/Projects/Python/The-Satellite-Project/src/commands): command modules
- [src/redis_client.py](/E:/Projects/Python/The-Satellite-Project/src/redis_client.py): subscription storage
- [src/webhook_manager.py](/E:/Projects/Python/The-Satellite-Project/src/webhook_manager.py): webhook creation and reuse

## Transparency

Everything in this README is written by Codex, other than this Transparency Notice. Codex has also contributed to the codebase, which is why the project structure differs from my previous projects so much. It's definitely a little odd from my side, but I wanted to try the waters. Hey, I at least learned something new though.