from __future__ import annotations

from discord import Interaction
from discord.ext import commands

from src.buttons import make_confirm_cancel_view
from src.checks import requires_manage_channels
from src.redis_client import delete_subscription, get_subscription
from src.webhook_manager import delete_webhook


def setup(bot: commands.Bot) -> None:
    @bot.hybrid_command(
        name="unmod",
        description="Unbind the mod channel in the server from the satellite network.",
    )
    @requires_manage_channels()
    async def unbind(ctx: commands.Context[commands.Bot]) -> None:
        guild = ctx.guild

        if guild is None:
            await ctx.send("This command can only be used in a server.")
            return

        subscription = await get_subscription(guild.id)
        if subscription is None:
            await ctx.send(
                f"**{guild.name}** doesn't have a channel that is on the satellite network.\n"
                "If you want to add this channel to the satellite network, use the `bind` command."
            )
            return

        async def on_confirm(interaction: Interaction) -> None:
            # should probably delete the webhook too
            await delete_webhook(bot, ctx.channel)
            await delete_subscription(guild.id)
            await interaction.followup.send(
                f"Unbound **{guild.name}** from the satellite network."
            )

        async def on_cancel(interaction: Interaction) -> None:
            await interaction.followup.send(
                f"Okay, **{guild.name}** will remain bound to the satellite network."
            )

        view = make_confirm_cancel_view(
            owner_id=ctx.author.id,
            confirm_label="Yes, unbind!",
            cancel_label="No...",
            on_confirm=on_confirm,
            on_cancel=on_cancel,
        )

        view.message = await ctx.send(
            f"Do you wish to unbind **{guild.name}** from the satellite?",
            view=view,
        )
