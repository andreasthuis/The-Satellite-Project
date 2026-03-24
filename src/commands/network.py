from __future__ import annotations

import discord
from discord.ext import commands

from src.redis_client import list_subscriptions


def build_network_embed(
    bot: commands.Bot,
    current_guild: discord.Guild,
    subscriptions: dict[str, dict[str, object]],
) -> discord.Embed:
    embed = discord.Embed(
        title="The Satellite Network",
        description=f"{len(subscriptions)} server(s) are currently bound to the network.",
        color=discord.Color.blurple(),
    )

    lines: list[str] = []
    for guild_id, subscription in sorted(
        subscriptions.items(),
        key=lambda item: (
            not bool(item[1]["active"]),
            bot.get_guild(int(item[0])).name.lower() if bot.get_guild(int(item[0])) else item[0],
        ),
    ):
        guild = bot.get_guild(int(guild_id))
        guild_name = guild.name if guild is not None else f"Unknown Guild ({guild_id})"
        marker = "This server" if guild is not None and guild.id == current_guild.id else guild_name
        state = "🔗 Connected" if subscription["active"] else "⛓️‍💥 Disconnected" # i guess i'll deal with it
        lines.append(
            f"**{marker}**: {state}"
        )

    embed.description = "\n".join(lines) if lines else "No servers are currently bound to the network."
    return embed


def setup(bot: commands.Bot) -> None:
    @bot.hybrid_command(
        name="network",
        description="Show all servers currently bound to the satellite network.",
    )
    async def network(ctx: commands.Context[commands.Bot]) -> None:
        guild = ctx.guild
        if guild is None:
            await ctx.send("This command can only be used in a server.")
            return

        subscriptions = await list_subscriptions()
        embed = build_network_embed(bot, guild, subscriptions)
        await ctx.send(embed=embed)
