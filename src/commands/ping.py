from __future__ import annotations

from discord.ext import commands

def setup(bot: commands.Bot) -> None:
    @bot.hybrid_command(name="ping", description="Ping the bot for a response.")
    async def ping(ctx: commands.Context[commands.Bot]) -> None:
        await ctx.send("Pong!")
