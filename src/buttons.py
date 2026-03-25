from __future__ import annotations

import discord
import datetime
from collections.abc import Awaitable, Callable

InteractionHandler = Callable[[discord.Interaction], Awaitable[None]]

class ModActionsView(discord.ui.View):
    def __init__(self, target_id: int = 0):
        super().__init__(timeout=None)
        self.target_id = target_id
        self.timeout_user.custom_id = f"mod:timeout:{target_id}"
        self.ban_user.custom_id = f"mod:ban:{target_id}"

    @discord.ui.button(label="Global Timeout (10m)", style=discord.ButtonStyle.secondary)
    async def timeout_user(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.moderate_members:
            return await interaction.response.send_message("Missing Permissions", ephemeral=True)

        user_id = int(button.custom_id.split(":")[-1])
        until = discord.utils.utcnow() + datetime.timedelta(minutes=10)
        
        success_count = 0
        failed_count = 0

        for guild in interaction.client.guilds:
            member = guild.get_member(user_id)
            if member:
                try:
                    if guild.me.top_role > member.top_role:
                        await member.timeout(until, reason=f"Global Timeout by {interaction.user}")
                        success_count += 1
                    else:
                        failed_count += 1
                except discord.Forbidden:
                    failed_count += 1

        await interaction.response.send_message(
            f"**Global Action Result:**\n"
            f"Timed out in **{success_count}** servers.\n"
            f"Failed in **{failed_count}** servers (Permissions/Hierarchy).", 
            ephemeral=True
        )

    @discord.ui.button(label="Global Ban", style=discord.ButtonStyle.danger)
    async def ban_user(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.ban_members:
            return await interaction.response.send_message("Missing Permissions", ephemeral=True)

        user_id = int(button.custom_id.split(":")[-1])
        success_count = 0

        for guild in interaction.client.guilds:
            try:
                await guild.ban(discord.Object(id=user_id), reason=f"Global Ban by {interaction.user}")
                success_count += 1
            except discord.HTTPException:
                continue

        await interaction.response.send_message(
            f"**Global Ban Result:**\nBanned from **{success_count}** servers.", 
            ephemeral=True
        )


class ConfirmCancelView(discord.ui.View):
    """Used for setup commands like !mod bind."""
    def __init__(
        self,
        *,
        owner_id: int | None = None,
        timeout: float = 180,
        confirm_label: str = "Confirm",
        cancel_label: str = "Cancel",
        on_confirm: InteractionHandler | None = None,
        on_cancel: InteractionHandler | None = None,
    ) -> None:
        super().__init__(timeout=timeout)
        self.owner_id = owner_id
        self.on_confirm = on_confirm
        self.on_cancel = on_cancel
        self.message: discord.Message | None = None

        self.confirm_button.label = confirm_label
        self.cancel_button.label = cancel_label

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.owner_id is None or interaction.user.id == self.owner_id:
            return True
        await interaction.response.send_message("This isn't your menu!", ephemeral=True)
        return False

    async def disable_all(self, interaction: discord.Interaction) -> None:
        for item in self.children:
            item.disabled = True
        if interaction.response.is_done():
            await interaction.edit_original_response(view=self)
        else:
            await interaction.response.edit_message(view=self)

    @discord.ui.button(style=discord.ButtonStyle.success)
    async def confirm_button(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self.disable_all(interaction)
        if self.on_confirm: await self.on_confirm(interaction)

    @discord.ui.button(style=discord.ButtonStyle.secondary)
    async def cancel_button(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self.disable_all(interaction)
        if self.on_cancel: await self.on_cancel(interaction)

# --- HELPER FUNCTIONS ---

def make_confirm_cancel_view(**kwargs) -> ConfirmCancelView:
    return ConfirmCancelView(**kwargs)

def make_mod_log_view(target_id: int) -> ModActionsView:
    return ModActionsView(target_id=target_id)