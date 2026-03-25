from __future__ import annotations

from discord import Interaction, TextChannel, app_commands
from discord.ext import commands

from src.buttons import make_confirm_cancel_view
from src.checks import requires_manage_channels
from src.redis_client import get_mod_channel, set_mod_channel
from src.webhook_manager import get_webhook


def setup(bot: commands.Bot) -> None:
    @bot.hybrid_command(
        name="mod",
        description="Bind this channel as the server's moderation channel.",
    )
    @requires_manage_channels()
    @app_commands.describe(
        use_webhook="Use a channel webhook for logs instead of normal bot messages."
    )
    async def bind(ctx: commands.Context[commands.Bot], use_webhook: bool = True) -> None:
        guild = ctx.guild
        if guild is None:
            await ctx.send("This command can only be used in a server.")
            return

        existing = await get_mod_channel(guild.id)
        if existing is not None:
            await ctx.send(
                f"Moderation channel already bound at <#{existing['channel_id']}>.\n"
                f"Use `rebindmod` to move it."
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

            await set_mod_channel(
                interaction.guild.id,
                interaction.channel.id,
                webhook=webhook_url,
            )

            mode = "using a webhook" if webhook_url else "using bot messages"
            await interaction.followup.send(
                f"{interaction.channel.mention} is now the moderation channel, {mode}."
            )

        async def on_cancel(interaction: Interaction) -> None:
            await interaction.followup.send("Cancelled.")

        view = make_confirm_cancel_view(
            owner_id=ctx.author.id,
            confirm_label="Yes, bind mod channel",
            cancel_label="Cancel",
            on_confirm=on_confirm,
            on_cancel=on_cancel,
        )

        mode_label = "webhook logging" if use_webhook else "bot logging"
        view.message = await ctx.send(
            f"Bind {ctx.channel.mention} as the moderation channel with {mode_label}?",
            view=view,
        )