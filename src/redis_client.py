from __future__ import annotations

import json
from typing import TypedDict

from redis.asyncio import Redis

SUBSCRIPTIONS_KEY = "subscriptions"
RELAY_KEY_PREFIX = "relay"
REFERENCE_KEY_PREFIX = "reference"


class Subscription(TypedDict):
    channel_id: int
    active: bool
    webhook: str | None


class RelayedMessage(TypedDict):
    guild_id: int
    channel_id: int
    message_id: int
    author_id: int


redis: Redis | None = None


def parse_subscription(raw_subscription: str) -> Subscription:
    parsed = json.loads(raw_subscription)
    return {
        "channel_id": int(parsed["channel_id"]),
        "active": bool(parsed.get("active", True)),
        "webhook": parsed.get("webhook"),
    }


def parse_relayed_message(entry: dict[str, int | str]) -> RelayedMessage:
    return {
        "guild_id": int(entry["guild_id"]),
        "channel_id": int(entry["channel_id"]),
        "message_id": int(entry["message_id"]),
        "author_id": int(entry["author_id"]),
    }


def relay_key(source_message_id: int) -> str:
    return f"{RELAY_KEY_PREFIX}:{source_message_id}"


def reference_key(relayed_message_id: int) -> str:
    return f"{REFERENCE_KEY_PREFIX}:{relayed_message_id}"


async def init_redis(redis_url: str) -> Redis:
    global redis

    if redis is None:
        client = Redis.from_url(redis_url, encoding="utf-8", decode_responses=True)
        await client.ping()
        redis = client

    return redis


def get_redis() -> Redis:
    if redis is None:
        raise RuntimeError("Redis has not been initialized yet.")
    return redis


async def close_redis() -> None:
    global redis

    if redis is not None:
        await redis.aclose()
        redis = None


async def get_subscription(guild_id: int) -> Subscription | None:
    redis_client = get_redis()
    raw_subscription = await redis_client.hget(SUBSCRIPTIONS_KEY, str(guild_id))
    if raw_subscription is None:
        return None

    return parse_subscription(raw_subscription)


async def set_subscription(
    guild_id: int,
    channel_id: int,
    *,
    active: bool = True,
    webhook: str | None = None,
) -> Subscription:
    redis_client = get_redis()
    subscription: Subscription = {
        "channel_id": channel_id,
        "active": active,
        "webhook": webhook,
    }

    await redis_client.hset(SUBSCRIPTIONS_KEY, str(guild_id), json.dumps(subscription))
    return subscription


async def set_subscription_active(guild_id: int, active: bool) -> Subscription:
    subscription = await get_subscription(guild_id)
    if subscription is None:
        raise RuntimeError("This server is not subscribed to the satellite network yet.")

    return await set_subscription(
        guild_id,
        subscription["channel_id"],
        active=active,
        webhook=subscription["webhook"],
    )


async def delete_subscription(guild_id: int) -> None:
    redis_client = get_redis()
    await redis_client.hdel(SUBSCRIPTIONS_KEY, str(guild_id))


async def list_subscriptions() -> dict[str, Subscription]:
    redis_client = get_redis()
    raw_subscriptions = await redis_client.hgetall(SUBSCRIPTIONS_KEY)
    return {
        guild_id: parse_subscription(raw_subscription)
        for guild_id, raw_subscription in raw_subscriptions.items()
    }


async def set_relayed_messages(
    source_message: RelayedMessage,
    relayed_messages: list[RelayedMessage],
) -> None:
    redis_client = get_redis()
    source_dump = json.dumps(source_message)

    await redis_client.set(relay_key(source_message["message_id"]), json.dumps(relayed_messages))
    await redis_client.mset(
        {reference_key(relayed_message["message_id"]): source_dump for relayed_message in relayed_messages}
    )


async def get_relay_source(relayed_message_id: int) -> RelayedMessage | None:
    redis_client = get_redis()
    raw_relay_source = await redis_client.get(reference_key(relayed_message_id))
    if raw_relay_source is None:
        return None

    return parse_relayed_message(json.loads(raw_relay_source))


async def get_relayed_messages(source_message_id: int) -> list[RelayedMessage]:
    redis_client = get_redis()
    raw_relayed_messages = await redis_client.get(relay_key(source_message_id))
    if raw_relayed_messages is None:
        return []

    parsed = json.loads(raw_relayed_messages)
    return [parse_relayed_message(entry) for entry in parsed]


async def delete_relayed_messages(source_message_id: int) -> None:
    redis_client = get_redis()
    await redis_client.delete(relay_key(source_message_id))


"""
HASHMAP subscriptions
[GuildId]: {
    channel_id: int,
    active: bool,
    webhook: str | None,
}
"""
