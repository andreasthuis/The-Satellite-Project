from __future__ import annotations

import discord
from discord.ext import commands

from src.checks import requires_manage_channels
from src.redis_client import get_subscription, set_subscription_active


async def get_satellite_channel(
    bot: commands.Bot,
    channel_id: int,
) -> discord.abc.Messageable | None:
    channel = bot.get_channel(channel_id)
    if channel is None:
        try:
            channel = await bot.fetch_channel(channel_id)
        except discord.HTTPException:
            return None

    if not isinstance(channel, discord.abc.Messageable):
        return None

    return channel


def setup(bot: commands.Bot) -> None:
    @bot.hybrid_command(
        name="connect",
        description="Reconnect this server to the satellite network.",
    )
    @requires_manage_channels()
    async def connect(ctx: commands.Context[commands.Bot]) -> None:
        guild = ctx.guild
        if guild is None:
            await ctx.send("This command can only be used in a server.")
            return

        subscription = await get_subscription(guild.id)
        if subscription is None:
            await ctx.send(
                "This server is not bound to the satellite network yet. Use the `bind` command first."
            )
            return

        if subscription["active"]:
            await ctx.send("This server is already connected to the satellite network.")
            return

        updated_subscription = await set_subscription_active(guild.id, True)
        satellite_channel = await get_satellite_channel(bot, updated_subscription["channel_id"])
        if satellite_channel is not None:
            await satellite_channel.send("You now are connected to the satellite network.")

        if ctx.channel.id != updated_subscription["channel_id"]:
            await ctx.send(
                f"Reconnected this server to the satellite network in <#{updated_subscription['channel_id']}>."
            )

    @bot.hybrid_command(
        name="disconnect",
        description="Disconnect this server from the satellite network without unbinding it.",
    )
    @requires_manage_channels()
    async def disconnect(ctx: commands.Context[commands.Bot]) -> None:
        guild = ctx.guild
        if guild is None:
            await ctx.send("This command can only be used in a server.")
            return

        subscription = await get_subscription(guild.id)
        if subscription is None:
            await ctx.send(
                "This server is not bound to the satellite network yet. Use the `bind` command first."
            )
            return

        if not subscription["active"]:
            await ctx.send("This server is already disconnected from the satellite network.")
            return

        updated_subscription = await set_subscription_active(guild.id, False)
        satellite_channel = await get_satellite_channel(bot, updated_subscription["channel_id"])
        if satellite_channel is not None:
            await satellite_channel.send("You are no longer connected to the satellite network.")

        if ctx.channel.id != updated_subscription["channel_id"]:
            await ctx.send(
                f"Disconnected this server from the satellite network in <#{updated_subscription['channel_id']}>."
            )
