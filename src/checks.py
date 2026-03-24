from __future__ import annotations

from discord.ext import commands


def requires_manage_channels() -> commands.Check:
    async def predicate(ctx: commands.Context[commands.Bot]) -> bool:
        if ctx.guild is None:
            raise commands.NoPrivateMessage("This command can only be used in a server.")

        permissions = getattr(ctx.author, "guild_permissions", None)
        if permissions is None or not permissions.manage_channels:
            raise commands.MissingPermissions(["manage_channels"])

        return True

    return commands.check(predicate)
