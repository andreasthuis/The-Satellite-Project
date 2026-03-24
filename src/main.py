from __future__ import annotations

import asyncio
import logging
import os

import discord
from discord.ext import commands
from dotenv import load_dotenv

from src.commands import register_commands
from src.redis_client import (
    Subscription,
    close_redis,
    get_subscription,
    init_redis,
    list_subscriptions,
)

LOGGER = logging.getLogger(__name__)
ALLOWED_MENTIONS = discord.AllowedMentions.none()
ALLOWED_MENTIONS.users = True


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


def build_relay_content(message: discord.Message) -> str:
    parts: list[str] = []
    if message.clean_content:
        parts.append(message.clean_content)

    if message.attachments:
        parts.extend(attachment.url for attachment in message.attachments)

    if not parts:
        parts.append("*Sent a message with unsupported content.*")
        
    parts.append(f"-# by @{message.author.name} from **{message.guild.name}**")

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


async def relay_to_subscription(
    bot: SatelliteBot,
    message: discord.Message,
    subscription: Subscription,
) -> None:
    relay_content = build_relay_content(message)
    author_name = message.author.display_name
    source_name = message.guild.name if message.guild is not None else "Unknown Server"

    if subscription["webhook"]:
        try:
            webhook = discord.Webhook.from_url(subscription["webhook"], client=bot)
            await webhook.send(
                relay_content,
                username=f"{author_name}",
                avatar_url=message.author.display_avatar.url,
                allowed_mentions=ALLOWED_MENTIONS,
            )
            return
        except discord.HTTPException:
            LOGGER.warning(
                "Webhook relay failed for channel %s, falling back to bot message.",
                subscription["channel_id"],
            )

    target_channel = await get_target_channel(bot, subscription)
    if target_channel is None:
        return

    await target_channel.send(
        f"**{author_name}** ({source_name})\n{relay_content}",
        allowed_mentions=ALLOWED_MENTIONS,
    )


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
        relay_tasks: list[tuple[str, asyncio.Task[None]]] = []

        for guild_id, subscription in subscriptions.items():
            if not subscription["active"]:
                continue
            if int(guild_id) == guild.id:
                continue

            LOGGER.info("Distributing message by %s", message.author.name)
            relay_tasks.append(
                (guild_id, asyncio.create_task(relay_to_subscription(bot, message, subscription)))
            )

        if not relay_tasks:
            return

        results = await asyncio.gather(
            *(task for _, task in relay_tasks),
            return_exceptions=True,
        )
        for (guild_id, _), result in zip(relay_tasks, results, strict=True):
            if isinstance(result, Exception):
                LOGGER.exception(
                    "Relay to guild %s failed.",
                    guild_id,
                    exc_info=result,
                )

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
