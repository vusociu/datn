import redis
from typing import Any, Optional


class RedisService:
    _instance = None  # singleton (dùng chung connection)

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        password: Optional[str] = None,
        decode_responses: bool = True,
    ):
        if hasattr(self, "_initialized"):
            return

        self.client = redis.Redis(
            host=host,
            port=port,
            db=db,
            password=password,
            decode_responses=decode_responses,
        )

        # test connection
        self.client.ping()
        self._initialized = True

    # ---------- BASIC ----------
    def set(self, key: str, value: Any, ex: Optional[int] = None):
        """Set key with optional TTL (seconds)"""
        return self.client.set(name=key, value=value, ex=ex)

    def get(self, key: str):
        return self.client.get(key)

    def delete(self, key: str):
        return self.client.delete(key)

    def exists(self, key: str) -> bool:
        return self.client.exists(key) == 1

    # ---------- HASH ----------
    def hset(self, name: str, mapping: dict):
        return self.client.hset(name, mapping=mapping)

    def hgetall(self, name: str) -> dict:
        return self.client.hgetall(name)

    # ---------- LIST / QUEUE ----------
    def lpush(self, key: str, value: Any):
        return self.client.lpush(key, value)

    def rpush(self, key: str, value: Any):
        return self.client.rpush(key, value)

    def lpop(self, key: str):
        return self.client.lpop(key)

    # ---------- SET ----------
    def sadd(self, key: str, *values):
        return self.client.sadd(key, *values)

    def smembers(self, key: str):
        return self.client.smembers(key)

    # ---------- PUB / SUB ----------
    def publish(self, channel: str, message: str):
        return self.client.publish(channel, message)

    def subscribe(self, channel: str):
        pubsub = self.client.pubsub()
        pubsub.subscribe(channel)
        return pubsub

    # ---------- UTILS ----------
    def ping(self) -> bool:
        return self.client.ping()