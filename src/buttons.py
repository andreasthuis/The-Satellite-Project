from __future__ import annotations

from collections.abc import Awaitable, Callable

import discord

InteractionHandler = Callable[[discord.Interaction], Awaitable[None]]


class ConfirmCancelView(discord.ui.View):
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

        await interaction.response.send_message(
            "Only the user who started this action can use these buttons.",
            ephemeral=True,
        )
        return False

    async def disable_all(self, interaction: discord.Interaction) -> None:
        for item in self.children:
            item.disabled = True

        if interaction.response.is_done():
            await interaction.edit_original_response(view=self)
        else:
            await interaction.response.edit_message(view=self)

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass

    @discord.ui.button(style=discord.ButtonStyle.success, custom_id="confirm")
    async def confirm_button(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        await self.disable_all(interaction)
        if self.on_confirm is not None:
            await self.on_confirm(interaction)

    @discord.ui.button(style=discord.ButtonStyle.secondary, custom_id="cancel")
    async def cancel_button(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        await self.disable_all(interaction)
        if self.on_cancel is not None:
            await self.on_cancel(interaction)


def make_confirm_cancel_view(
    *,
    owner_id: int | None = None,
    timeout: float = 180,
    confirm_label: str = "Confirm",
    cancel_label: str = "Cancel",
    on_confirm: InteractionHandler | None = None,
    on_cancel: InteractionHandler | None = None,
) -> ConfirmCancelView:
    return ConfirmCancelView(
        owner_id=owner_id,
        timeout=timeout,
        confirm_label=confirm_label,
        cancel_label=cancel_label,
        on_confirm=on_confirm,
        on_cancel=on_cancel,
    )
