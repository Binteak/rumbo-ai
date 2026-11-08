import fakeredis
import pytest

from app.sessions import MemorySessionStore, RedisSessionStore


@pytest.fixture(params=["memory", "redis"])
def store(request):
    if request.param == "memory":
        return MemorySessionStore()
    return RedisSessionStore("redis://unused", client=fakeredis.FakeRedis())


def test_save_get_reset(store):
    assert store.get("s1") == []
    store.save("s1", [{"role": "user", "content": "hola"}])
    assert store.get("s1") == [{"role": "user", "content": "hola"}]
    store.reset("s1")
    assert store.get("s1") == []


def test_lock_prevents_concurrent_runs(store):
    first, second = store.lock("s1"), store.lock("s1")
    assert first.acquire(blocking=False)
    assert not second.acquire(blocking=False)
    first.release()
    assert second.acquire(blocking=False)
    second.release()


def test_redis_history_is_shared_between_replicas():
    server = fakeredis.FakeServer()
    replica_a = RedisSessionStore("redis://unused", client=fakeredis.FakeRedis(server=server))
    replica_b = RedisSessionStore("redis://unused", client=fakeredis.FakeRedis(server=server))
    replica_a.save("s1", [{"role": "user", "content": "Kioto"}])
    assert replica_b.get("s1")[0]["content"] == "Kioto"
    assert replica_a.redis.ttl("rumbo:session:s1") > 0
