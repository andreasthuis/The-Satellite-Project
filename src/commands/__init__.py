from __future__ import annotations

import importlib
from pathlib import Path
from types import ModuleType

from discord.ext import commands


async def register_commands(bot: commands.Bot) -> tuple[int, list[str]]:
    commands_dir = Path(__file__).resolve().parent

    failures: list[str] = []
    success = 0
    for command_file in sorted(commands_dir.glob("*.py")):
        if command_file.name == "__init__.py":
            continue

        module_name = command_file.stem
        print(f'Parsing command "{module_name}"')

        try:
            command_module: ModuleType = importlib.import_module(
                f"{__name__}.{module_name}"
            )
            setup = getattr(command_module, "setup", None)
            if setup is not None:
                result = setup(bot)
                if hasattr(result, "__await__"):
                    await result

                print(f'Parsed command "{module_name}"')
                success += 1
        except BaseException as e:
            failures.append(module_name)
            print(f"Failed to load command {module_name} with error: {e}")
    return success, failures
