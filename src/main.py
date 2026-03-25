from __future__ import annotations

import asyncio
import logging
import os
import re

import discord
from discord.ext import commands
from dotenv import load_dotenv

from src.buttons import ModActionsView

from src.commands import register_commands
from src.redis_client import (
    RelayedMessage,
    Subscription,
    close_redis,
    delete_relayed_messages,
    get_relay_source,
    get_relayed_messages,
    get_subscription,
    init_redis,
    list_subscriptions,
    set_relayed_messages,
)

LOGGER = logging.getLogger(__name__)
ALLOWED_MENTIONS = discord.AllowedMentions.none()
ALLOWED_MENTIONS.users = True
RELAY_AUTHOR_RE = re.compile(r"^-# by @(.+?) in \*\*(.+?)\*\*$")
URL_RE = re.compile(r"(?<!<)(https?://[^\s>]+)(?!>)")


class SatelliteBot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = True

        prefix = os.getenv("COMMAND_PREFIX", "!").strip() or "!"
        super().__init__(command_prefix=commands.when_mentioned_or(prefix), intents=intents)

    async def setup_hook(self) -> None:
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0").strip()
        await init_redis(redis_url)
        success_count, failed_commands = await register_commands(self)
        total_count = success_count + len(failed_commands)
        noun = "command" if total_count == 1 else "commands"
        LOGGER.info(
            "Parsed %s of %s %s successfully.",
            success_count,
            total_count,
            noun,
        )
        if failed_commands:
            LOGGER.warning(
                "Failed to parse %s command(s): %s",
                len(failed_commands),
                ", ".join(failed_commands),
            )

        await sync_command_tree(self)
        
        from src.buttons import ModActionsView
        self.add_view(ModActionsView())

    async def close(self) -> None:
        await close_redis()
        await super().close()


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


def get_discord_token() -> str:
    token = os.getenv("DISCORD_TOKEN", "").strip()
    if not token:
        raise RuntimeError("DISCORD_TOKEN is required to start the bot.")
    return token


def get_command_sync_mode() -> str:
    mode = os.getenv("COMMAND_SYNC_MODE", "guild").strip().lower() or "guild"
    if mode not in {"none", "guild", "global"}:
        raise RuntimeError("COMMAND_SYNC_MODE must be one of: none, guild, global.")
    return mode


def get_dev_guild_id() -> int | None:
    raw_guild_id = os.getenv("DEV_GUILD_ID", "").strip()
    if not raw_guild_id:
        return None
    return int(raw_guild_id)


async def sync_command_tree(bot: SatelliteBot) -> None:
    mode = get_command_sync_mode()

    if mode == "none":
        LOGGER.info("Skipping command tree sync.")
        return

    if mode == "global":
        LOGGER.info("Synchronizing global command tree")
        await bot.tree.sync()
        LOGGER.info("Synchronized global command tree")
        return

    dev_guild_id = get_dev_guild_id()
    if dev_guild_id is None:
        LOGGER.info(
            "Skipping guild command sync because DEV_GUILD_ID is not set. "
            "Set COMMAND_SYNC_MODE=global to publish globally."
        )
        return

    guild = discord.Object(id=dev_guild_id)
    bot.tree.copy_global_to(guild=guild)
    LOGGER.info("Synchronizing command tree to development guild %s", dev_guild_id)
    await bot.tree.sync(guild=guild)
    LOGGER.info("Synchronized command tree to development guild %s", dev_guild_id)


async def resolve_referenced_message(message: discord.Message) -> discord.Message | None:
    reference = message.reference
    if reference is None or reference.message_id is None:
        return None

    if isinstance(reference.resolved, discord.Message):
        return reference.resolved

    if hasattr(message.channel, "fetch_message"):
        try:
            return await message.channel.fetch_message(reference.message_id)
        except discord.HTTPException:
            return None

    return None


def wrap_preview_links(text: str) -> str:
    return URL_RE.sub(r"<\1>", text)


def extract_preview_text(content: str) -> str:
    lines = [line.rstrip() for line in content.splitlines()]
    cleaned_lines: list[str] = []

    quote_closed = False
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("-# by @"):
            quote_closed = True
            continue
        if stripped.startswith("> -# *Replying to a message by"):
            continue
        if stripped.startswith(">") and not quote_closed:
            continue
        cleaned_lines.append(stripped)

    preview = " ".join(cleaned_lines).strip()
    preview = wrap_preview_links(preview)
    if len(preview) > 120:
        preview = f"{preview[:117]}..."
    return preview


def get_displayed_author(message: discord.Message) -> str:
    lines = [line.strip() for line in message.content.splitlines() if line.strip()]
    for line in reversed(lines):
        match = RELAY_AUTHOR_RE.match(line)
        if match:
            return f"@{match.group(1)}"
    return f"{message.author.display_name} (@{message.author.name})"


def build_reply_preview(reply_message: discord.Message) -> str:
    preview = extract_preview_text(reply_message.content)
    if not preview and reply_message.attachments:
        preview = "[attachment]"
    if not preview:
        preview = "[message unavailable]"
    return preview


async def build_relay_content(
    message: discord.Message,
    *,
    include_reply_quote: bool,
    reply_ping_author_id: int | None = None,
) -> str:
    parts: list[str] = []

    reply_message = await resolve_referenced_message(message)
    if include_reply_quote and reply_message is not None:
        if reply_ping_author_id is not None:
            reply_author = (f"<@{reply_ping_author_id}>")
        else:
            reply_author = get_displayed_author(reply_message)
        reply_preview = build_reply_preview(reply_message)
        parts.append(f"> -# *Replying to a message by {reply_author}*")
        parts.append(f"> {reply_preview}")

    if message.content:
        parts.append(message.content)

    if message.attachments:
        parts.extend(attachment.url for attachment in message.attachments)

    if not any(part and not part.startswith(">") for part in parts):
        parts.append("*Sent a message with unsupported content.*")

    guild_name = message.guild.name if message.guild is not None else "Unknown Server"
    parts.append(f"-# by @{message.author.name} in **{guild_name}**")

    return "\n".join(parts)


async def get_target_channel(
    bot: SatelliteBot, subscription: Subscription
) -> discord.abc.Messageable | None:
    channel_id = subscription["channel_id"]
    channel = bot.get_channel(channel_id)
    if channel is None:
        try:
            channel = await bot.fetch_channel(channel_id)
        except discord.HTTPException:
            LOGGER.warning("Failed to fetch destination channel %s.", channel_id)
            return None

    if not isinstance(channel, discord.abc.Messageable):
        LOGGER.warning("Destination channel %s is not messageable.", channel_id)
        return None

    return channel


async def get_relay_reply_target(
    bot: SatelliteBot,
    source_message: discord.Message,
    subscription: Subscription,
) -> discord.Message | None:
    reference = source_message.reference
    if reference is None or reference.message_id is None:
        return None

    relayed_messages = await get_relayed_messages(reference.message_id)
    target_entry = next(
        (
            relayed_message
            for relayed_message in relayed_messages
            if relayed_message["channel_id"] == subscription["channel_id"]
        ),
        None,
    )

    if target_entry is None:
        target_entry = await get_relay_source(reference.message_id)
        if target_entry is None:
            return None

    channel = bot.get_channel(target_entry["channel_id"])
    if channel is None:
        try:
            channel = await bot.fetch_channel(target_entry["channel_id"])
        except discord.HTTPException:
            return None

    if not hasattr(channel, "fetch_message"):
        return None

    try:
        return await channel.fetch_message(target_entry["message_id"])
    except discord.HTTPException:
        return None


async def get_simulated_reply_author_id(
    source_message: discord.Message,
    subscription: Subscription,
) -> int | None:
    reference = source_message.reference
    if reference is None or reference.message_id is None:
        return None

    relayed_messages = await get_relayed_messages(reference.message_id)
    target_entry = next(
        (
            relayed_message
            for relayed_message in relayed_messages
            if relayed_message["channel_id"] == subscription["channel_id"]
        ),
        None,
    )
    if target_entry is not None:
        return target_entry["author_id"]

    relay_source = await get_relay_source(reference.message_id)
    if relay_source is not None:
        return relay_source["author_id"]

    return None


async def relay_to_subscription(
    bot: SatelliteBot,
    message: discord.Message,
    destination_guild_id: int,
    subscription: Subscription,
) -> RelayedMessage | None:
    reply_ping_author_id = None
    is_webhook_message = message.reference.resolved.webhook_id is not None if message.reference and message.reference.resolved else False
    if bot.user in message.mentions or is_webhook_message:
        reply_ping_author_id = await get_simulated_reply_author_id(message, subscription)
        
    if subscription["webhook"]:
        relay_content = await build_relay_content(
            message,
            include_reply_quote=True,
            reply_ping_author_id=reply_ping_author_id,
        )
        try:
            webhook = discord.Webhook.from_url(subscription["webhook"], client=bot)
            relayed_message = await webhook.send(
                relay_content,
                username=f"{message.author.display_name}",
                avatar_url=message.author.display_avatar.url,
                allowed_mentions=ALLOWED_MENTIONS,
                wait=True,
            )

            return {
                "guild_id": destination_guild_id,
                "channel_id": subscription["channel_id"],
                "message_id": relayed_message.id,
                "author_id": message.author.id,
            }
        except discord.HTTPException:
            LOGGER.warning(
                "Webhook relay failed for channel %s, falling back to bot message.",
                subscription["channel_id"],
            )

    target_channel = await get_target_channel(bot, subscription)
    if target_channel is None:
        return None

    reply_target = await get_relay_reply_target(bot, message, subscription)
    relay_content = await build_relay_content(
        message,
        include_reply_quote=reply_target is None,
    )

    if reply_target is not None:
        relayed_message = await reply_target.reply(
            relay_content,
            allowed_mentions=ALLOWED_MENTIONS,
            stickers=message.stickers,
            mention_author=reply_ping_author_id is not None,
        )
    else:
        relayed_message = await target_channel.send(
            relay_content,
            allowed_mentions=ALLOWED_MENTIONS,
            stickers=message.stickers,
        )
    return {
        "guild_id": destination_guild_id,
        "channel_id": subscription["channel_id"],
        "message_id": relayed_message.id,
        "author_id": message.author.id,
    }


async def edit_relayed_message(
    bot: SatelliteBot,
    source_message: discord.Message,
    relayed_message: RelayedMessage,
) -> None:
    destination_subscription = await get_subscription(relayed_message["guild_id"])
    if destination_subscription is None:
        return

    if destination_subscription["webhook"]:
        reply_ping_author_id = await get_simulated_reply_author_id(
            source_message,
            destination_subscription,
        )
        relay_content = await build_relay_content(
            source_message,
            include_reply_quote=True,
            reply_ping_author_id=reply_ping_author_id,
        )
        webhook = discord.Webhook.from_url(destination_subscription["webhook"], client=bot)
        await webhook.edit_message(
            relayed_message["message_id"],
            content=relay_content,
            allowed_mentions=ALLOWED_MENTIONS,
        )
        return

    channel = bot.get_channel(relayed_message["channel_id"])
    if channel is None:
        channel = await bot.fetch_channel(relayed_message["channel_id"])

    if not hasattr(channel, "fetch_message"):
        return

    destination_message = await channel.fetch_message(relayed_message["message_id"])
    relay_content = await build_relay_content(
        source_message,
        include_reply_quote=destination_message.reference is None,
    )
    await destination_message.edit(content=relay_content, allowed_mentions=ALLOWED_MENTIONS)


async def delete_relayed_message(
    bot: SatelliteBot,
    relayed_message: RelayedMessage,
) -> None:
    destination_subscription = await get_subscription(relayed_message["guild_id"])
    if destination_subscription and destination_subscription["webhook"]:
        webhook = discord.Webhook.from_url(destination_subscription["webhook"], client=bot)
        await webhook.delete_message(relayed_message["message_id"])
        return

    channel = bot.get_channel(relayed_message["channel_id"])
    if channel is None:
        channel = await bot.fetch_channel(relayed_message["channel_id"])

    if not hasattr(channel, "fetch_message"):
        return

    destination_message = await channel.fetch_message(relayed_message["message_id"])
    await destination_message.delete()
    
async def send_mod_log(bot: SatelliteBot, guild: discord.Guild, content: str, target_id: int | None = None):
    from src.redis_client import get_mod_channel
    from src.buttons import make_mod_log_view
    
    sub = await get_mod_channel(guild.id)
    if not sub:
        return

    view = make_mod_log_view(target_id) if target_id else None
    
    channel_id = sub.get("channel_id")
    if not channel_id:
        return

    channel = guild.get_channel(int(channel_id))
    if channel is None:
        try:
            channel = await bot.fetch_channel(int(channel_id))
        except discord.HTTPException:
            LOGGER.error(f"Could not find mod channel {channel_id} in guild {guild.id}")
            return

    try:
        await channel.send(content, view=view)
    except discord.Forbidden:
        LOGGER.error(f"Missing permissions to send messages in {channel_id}")
    except discord.HTTPException as e:
        LOGGER.error(f"Failed to send mod log: {e}")

def build_bot() -> SatelliteBot:
    bot = SatelliteBot()

    @bot.event
    async def on_ready() -> None:
        user = bot.user
        if user is None:
            LOGGER.info("Bot connected, but the Discord user is not available yet.")
            return

        LOGGER.info("Logged in as %s (%s)", user.name, user.id)

    @bot.event
    async def on_message(message: discord.Message) -> None:
        if message.author.bot:
            return

        context = await bot.get_context(message)
        if context.valid:
            await bot.process_commands(message)
            return

        guild = message.guild
        if guild is None:
            return

        source_subscription = await get_subscription(guild.id)
        if source_subscription is None or not source_subscription["active"]:
            return

        if message.channel.id != source_subscription["channel_id"]:
            return

        subscriptions = await list_subscriptions()
        relay_tasks: list[tuple[str, asyncio.Task[RelayedMessage | None]]] = []

        for guild_id, subscription in subscriptions.items():
            if not subscription["active"]:
                continue
            if int(guild_id) == guild.id:
                continue

            LOGGER.info("Distributing message by %s", message.author.name)
            relay_tasks.append(
                (
                    guild_id,
                    asyncio.create_task(
                        relay_to_subscription(bot, message, int(guild_id), subscription)
                    ),
                )
            )

        if not relay_tasks:
            return

        results = await asyncio.gather(
            *(task for _, task in relay_tasks),
            return_exceptions=True,
        )

        stored_relays: list[RelayedMessage] = []
        for (guild_id, _), result in zip(relay_tasks, results, strict=True):
            if isinstance(result, Exception):
                LOGGER.exception(
                    "Relay to guild %s failed.",
                    guild_id,
                    exc_info=result,
                )
                continue

            if result is not None:
                stored_relays.append(result)

        if stored_relays:
            relay_source: RelayedMessage = {
                "guild_id": guild.id,
                "channel_id": message.channel.id,
                "message_id": message.id,
                "author_id": message.author.id,
            }
            await set_relayed_messages(relay_source, stored_relays)

    @bot.event
    async def on_message_edit(before: discord.Message, after: discord.Message) -> None:
        if after.author.bot:
            return
        
        if before.guild and before.content != after.content:
            await send_mod_log(
                bot,
                before.guild,
                f"**Edited:** {before.author} in {before.channel.mention}\n"
                f"**Before:** {before.content}\n**After:** {after.content}",
                target_id=before.author.id
            )

        if before.content == after.content and before.attachments == after.attachments:
            return

        relayed_messages = await get_relayed_messages(after.id)
        if relayed_messages:
            results = await asyncio.gather(
                *(edit_relayed_message(bot, after, rm) for rm in relayed_messages),
                return_exceptions=True,
            )
            
            for rm in relayed_messages:
                dest_guild = bot.get_guild(rm["guild_id"])
                if dest_guild:
                    await send_mod_log(
                        bot, 
                        dest_guild, 
                        f"**Relayed Message Edited** (Original by {after.author})\n"
                        f"**New Content:** {after.content[:500]}",
                        target_id=before.author.id
                    )

            for rm, res in zip(relayed_messages, results):
                if isinstance(res, Exception):
                    LOGGER.exception("Failed to edit relay in %s", rm["channel_id"], exc_info=res)

    @bot.event
    async def on_message_delete(message: discord.Message) -> None:
        if message.author and message.author.bot:
            return

        if message.guild:
            content_snippet = message.content or "[No text content]"
            await send_mod_log(
                bot,
                message.guild,
                f"**Deleted:** {message.author} in {message.channel.mention}\n{content_snippet}",
                target_id=before.author.id
            )

        relayed_messages = await get_relayed_messages(message.id)
        if relayed_messages:
            for rm in relayed_messages:
                dest_guild = bot.get_guild(rm["guild_id"])
                if dest_guild:
                    await send_mod_log(
                        bot, 
                        dest_guild, 
                        f"**Relayed Message Deleted** (Original by {message.author})\n"
                        f"**Content was:** {message.content[:500] if message.content else '[No text]'}",
                        target_id=before.author.id
                    )

            results = await asyncio.gather(
                *(delete_relayed_message(bot, rm) for rm in relayed_messages),
                return_exceptions=True,
            )
            await delete_relayed_messages(message.id)
            
            for rm, res in zip(relayed_messages, results):
                if isinstance(res, Exception):
                    LOGGER.exception("Failed to delete relay in %s", rm["channel_id"], exc_info=res)

    return bot

async def run_bot() -> None:
    load_dotenv()
    configure_logging()
    bot = build_bot()
    await bot.start(get_discord_token())


def main() -> None:
    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        LOGGER.info("Shutdown requested by user.")
