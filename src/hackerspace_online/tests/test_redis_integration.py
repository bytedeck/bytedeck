"""Integration tests that exercise the installed redis-py / kombu / django-redis
stack against a REAL redis server -- the paths the rest of the suite can't see.

The default test settings force ``LocMemCache`` (so django-redis never runs) and
no Celery worker runs during tests (tasks are only enqueued, never consumed).
So a redis-py / kombu / django-redis incompatibility -- e.g. a future redis-py
major bump like the redis 7 -> 8 one (#2202) -- sails through the unit suite
green even though it could break the cache or the broker in production. These
tests close that blind spot by exercising, against a live redis:

* the **django-redis cache client** (``RedisCache`` + ``DefaultClient``), and
* **kombu's redis broker transport**, producing AND consuming -- including an
  in-process Celery worker round-trip and the fanout control mailbox -- plus
  redis pub/sub (which celery's control plane uses).

They connect to the same redis the app uses (``settings.REDIS_HOST`` /
``settings.REDIS_PORT``) but on a dedicated db index (``REDIS_TEST_DB``), so they
never touch the app's broker/cache dbs (0/1/2), and they **skip** (rather than
fail) when redis is unreachable -- e.g. a bare local ``manage.py test`` with no
redis running. CI always has the ``redis:7`` service up (``REDIS_HOST=redis``),
so they run there on every push/PR.
"""
import time
import unittest

from celery import Celery
from django.conf import settings
from django.core.cache import cache
from django.test import SimpleTestCase, override_settings
from kombu import Connection
import redis

# A db index the app itself never uses (it uses 0=broker, 1=cache, 2=select2),
# so these tests are fully isolated and safe to flush.
REDIS_TEST_DB = 15

# Sentinel key the worker task bumps so the test can confirm consumption.
_SENTINEL_KEY = "bytedeck:redis_smoke:consumed"


def _redis_url(db=REDIS_TEST_DB):
    """Return the redis URL for the app's redis host/port at db ``db``."""
    return f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/{db}"


def _redis_conn_kwargs(**extra):
    """Return redis.Redis(**kwargs) for the dedicated test db, plus ``extra``."""
    return dict(host=settings.REDIS_HOST, port=int(settings.REDIS_PORT), db=REDIS_TEST_DB, **extra)


def _redis_reachable():
    """Return True if the app's redis answers PING, False otherwise.

    Used to skip (not fail) these tests when no redis is running -- so a bare
    local ``manage.py test`` still passes while CI (which has redis up) runs them.
    """
    try:
        redis.Redis(**_redis_conn_kwargs(socket_connect_timeout=3)).ping()
        return True
    except Exception:  # pragma: no cover - only hit when redis is absent; then the suite skips
        # Any connection/import error means "no usable redis here" -> skip.
        return False


def _flush_test_db():
    """Empty the dedicated test db so each test starts clean."""
    redis.Redis(**_redis_conn_kwargs()).flushdb()


# A throwaway Celery app pointed at the isolated test db. set_as_current=False is
# essential: this module is imported during the full test run, and we must not
# displace the real hackerspace_online.celery app as celery's "current app".
_smoke_app = Celery("bytedeck_redis_smoke", set_as_current=False)
_smoke_app.conf.update(
    broker_url=_redis_url(),
    result_backend=None,
    task_ignore_result=True,
    broker_connection_retry_on_startup=True,
    worker_hijack_root_logger=False,
)


@_smoke_app.task(name="bytedeck_redis_smoke.bump")
def _bump(amount):
    """Increment a redis sentinel, so the test can confirm a worker actually
    consumed + executed this task off the broker (no result backend is used)."""
    redis.Redis(**_redis_conn_kwargs()).incrby(_SENTINEL_KEY, amount)


class _RealRedisTestCase(SimpleTestCase):
    """Base case: skip the whole class unless the app's redis is reachable."""

    @classmethod
    def setUpClass(cls):
        """Skip every test in the class when redis is unreachable."""
        super().setUpClass()
        if not _redis_reachable():
            raise unittest.SkipTest(  # pragma: no cover - skip path, only when redis is down
                f"redis unreachable at {settings.REDIS_HOST}:{settings.REDIS_PORT} "
                f"(db {REDIS_TEST_DB}); skipping redis integration tests"
            )


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": _redis_url(),
            "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
            # No tenant KEY_FUNCTION here: it's pure string prefixing and never
            # touches redis-py, so it's irrelevant to redis-py compatibility.
        }
    }
)
class RedisCacheClientTests(_RealRedisTestCase):
    """The django-redis cache client works against real redis -- the cache path
    the unit suite never exercises (it forces LocMemCache)."""

    def setUp(self):
        """Start each test from an empty cache db (the dedicated test db)."""
        cache.clear()

    def test_cache__set_get_add_delete(self):
        """set/get round-trips a structured value; add respects existing keys; delete removes."""
        cache.set("smoke:k", {"a": 1, "b": [1, 2, 3]}, timeout=60)
        self.assertEqual(cache.get("smoke:k"), {"a": 1, "b": [1, 2, 3]})
        self.assertFalse(cache.add("smoke:k", "nope"))  # key already exists
        self.assertTrue(cache.add("smoke:new", "yes"))
        self.assertTrue(cache.delete("smoke:k"))
        self.assertIsNone(cache.get("smoke:k"))

    def test_cache__incr_and_ttl(self):
        """incr updates atomically and ttl reflects the set timeout (EXPIRE/TTL/INCRBY)."""
        cache.set("smoke:count", 1, timeout=100)
        self.assertEqual(cache.incr("smoke:count"), 2)
        self.assertEqual(cache.incr("smoke:count", 5), 7)
        ttl = cache.ttl("smoke:count")
        self.assertIsNotNone(ttl)
        self.assertTrue(0 < ttl <= 100)

    def test_cache__get_or_set_and_many(self):
        """get_or_set computes+stores a miss; set_many/get_many pipeline MSET/MGET."""
        self.assertEqual(cache.get_or_set("smoke:gos", lambda: "computed", timeout=60), "computed")
        self.assertEqual(cache.get("smoke:gos"), "computed")
        cache.set_many({"smoke:m1": 1, "smoke:m2": 2, "smoke:m3": 3}, timeout=60)
        self.assertEqual(
            cache.get_many(["smoke:m1", "smoke:m2", "smoke:m3"]),
            {"smoke:m1": 1, "smoke:m2": 2, "smoke:m3": 3},
        )

    def test_cache__delete_pattern_and_raw_client(self):
        """delete_pattern (SCAN) clears matching keys; the raw client ping/info parse (RESP-sensitive)."""
        cache.set("smoke:p:1", "a", timeout=60)
        cache.set("smoke:p:2", "b", timeout=60)
        self.assertGreaterEqual(cache.delete_pattern("smoke:p:*"), 2)
        raw = cache.client.get_client(write=True)
        self.assertTrue(raw.ping())
        self.assertIn("redis_version", raw.info())


class RedisBrokerTransportTests(_RealRedisTestCase):
    """kombu's redis broker transport + an in-process celery worker + redis
    pub/sub all work against real redis -- the broker paths the unit suite never
    exercises (it runs no worker; tasks are only enqueued)."""

    def setUp(self):
        """Flush the dedicated broker db before each test for isolation."""
        _flush_test_db()

    def test_kombu_transport__produce_and_consume(self):
        """A message produced to a kombu queue is consumed back through the redis transport."""
        with Connection(_redis_url()) as conn:
            queue = conn.SimpleQueue("smoke_kombu_q")
            queue.clear()
            queue.put({"hello": "world", "n": 42})
            message = queue.get(block=True, timeout=5)
            payload = message.payload
            message.ack()
            queue.close()
        self.assertEqual(payload, {"hello": "world", "n": 42})

    def test_redis_pubsub__publish_and_subscribe(self):
        """A published message reaches a subscriber (celery's control plane uses pub/sub)."""
        client = redis.Redis(**_redis_conn_kwargs())
        pubsub = client.pubsub()
        pubsub.subscribe("smoke:chan")
        # First message on a fresh subscription is the subscribe confirmation.
        self.assertEqual(pubsub.get_message(timeout=2)["type"], "subscribe")
        client.publish("smoke:chan", "ping")
        received = None
        deadline = time.time() + 3
        while time.time() < deadline:
            message = pubsub.get_message(timeout=1)
            if message and message["type"] == "message":
                received = message["data"]
                break
        pubsub.close()
        self.assertEqual(received, b"ping")

    def test_celery_worker__enqueue_consume_and_control_ping(self):
        """An in-process worker consumes a task enqueued via the redis broker and
        answers a control ping (the fanout/pidbox mailbox over pub/sub)."""
        from celery.contrib.testing.worker import start_worker

        control = redis.Redis(**_redis_conn_kwargs())
        control.delete(_SENTINEL_KEY)
        # perform_ping_check=False: no result backend is configured (matches prod).
        with start_worker(_smoke_app, perform_ping_check=False, loglevel="error"):
            _bump.delay(7)
            consumed = False
            deadline = time.time() + 30
            while time.time() < deadline:
                value = control.get(_SENTINEL_KEY)
                if value is not None and int(value) == 7:
                    consumed = True
                    break
                time.sleep(0.25)
            self.assertTrue(consumed, f"worker did not consume task; sentinel={control.get(_SENTINEL_KEY)!r}")
            replies = _smoke_app.control.ping(timeout=5)
            self.assertTrue(replies, "no worker responded to control.ping")
