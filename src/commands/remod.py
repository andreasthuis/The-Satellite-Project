from __future__ import annotations

from discord import Interaction, TextChannel, app_commands
from discord.ext import commands

from src.buttons import make_confirm_cancel_view
from src.checks import requires_manage_channels
from src.redis_client import get_subscription, set_subscription
from src.webhook_manager import get_webhook


def setup(bot: commands.Bot) -> None:
    @bot.hybrid_command(
        name="remod",
        description="Rebind the current mod channel to the satellite network for this server.",
    )
    @requires_manage_channels()
    @app_commands.describe(
        use_webhook="Use a channel webhook for relayed messages instead of normal bot messages."
    )
    async def rebind(ctx: commands.Context[commands.Bot], use_webhook: bool = True) -> None:
        guild = ctx.guild

        if guild is None:
            await ctx.send("This command can only be used in a server.")
            return

        subscription = await get_subscription(guild.id)
        if subscription is not None:
            if subscription["channel_id"] == ctx.channel.id and bool(subscription["webhook"]) == use_webhook:
                await ctx.send(f"{ctx.channel.mention} is already bound to the satellite with the requested delivery mode.")
                return

            async def on_confirm(interaction: Interaction) -> None:
                if interaction.guild is None or not isinstance(interaction.channel, TextChannel):
                    await interaction.followup.send(
                        "This command can only bind standard text channels.",
                        ephemeral=True,
                    )
                    return

                webhook_url: str | None = None
                if use_webhook:
                    try:
                        webhook = await get_webhook(bot, interaction.channel)
                    except RuntimeError as error:
                        await interaction.followup.send(str(error), ephemeral=True)
                        return

                    webhook_url = webhook.url

                await set_subscription(
                    interaction.guild.id,
                    interaction.channel.id,
                    webhook=webhook_url,
                )
                delivery_mode = "using a webhook" if webhook_url else "using bot messages"
                await interaction.followup.send(
                    f"Rebound {interaction.channel.mention} to the satellite network from "
                    f"<#{subscription['channel_id']}>, {delivery_mode}."
                )

            async def on_cancel(interaction: Interaction) -> None:
                await interaction.followup.send(
                    "Okay, the bound channel has not been changed from "
                    f"<#{subscription['channel_id']}>."
                )

            view = make_confirm_cancel_view(
                owner_id=ctx.author.id,
                confirm_label="Yes, rebind!",
                cancel_label="No...",
                on_confirm=on_confirm,
                on_cancel=on_cancel,
            )

            mode_label = "webhook relays" if use_webhook else "bot-message relays"
            view.message = await ctx.send(
                f"Do you wish to rebind this channel [{ctx.channel.mention}] to the satellite "
                f"from <#{subscription['channel_id']}> with {mode_label}?",
                view=view,
            )
            return

        async def on_confirm(interaction: Interaction) -> None:
            if interaction.guild is None or not isinstance(interaction.channel, TextChannel):
                await interaction.followup.send(
                    "This command can only bind standard text channels.",
                    ephemeral=True,
                )
                return

            webhook_url: str | None = None
            if use_webhook:
                try:
                    webhook = await get_webhook(bot, interaction.channel)
                except RuntimeError as error:
                    await interaction.followup.send(str(error), ephemeral=True)
                    return

                webhook_url = webhook.url

            await set_subscription(
                interaction.guild.id,
                interaction.channel.id,
                webhook=webhook_url,
            )
            delivery_mode = "using a webhook" if webhook_url else "using bot messages"
            await interaction.followup.send(
                f"Bound {interaction.channel.mention} to the satellite network, {delivery_mode}."
            )

        async def on_cancel(interaction: Interaction) -> None:
            await interaction.followup.send(
                f"Okay, **{guild.name}** has not been bound to the satellite network."
            )

        view = make_confirm_cancel_view(
            owner_id=ctx.author.id,
            confirm_label="Yes, bind!",
            cancel_label="No...",
            on_confirm=on_confirm,
            on_cancel=on_cancel,
        )

        mode_label = "webhook relays" if use_webhook else "bot-message relays"
        view.message = await ctx.send(
            f"Do you wish to bind this channel [{ctx.channel.mention}] to the satellite with {mode_label}?",
            view=view,
        )
