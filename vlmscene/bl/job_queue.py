"""Message queue for the distributed mode — how the API, ingest and caption workers talk.

`RabbitMQJobQueue` talks to RabbitMQ through pika and imports it lazily, so unit
tests and the batch CLI never need a broker. Queues are quorum queues with a
delivery limit: a handler that keeps failing on the same message has it
dead-lettered to `DEAD_LETTER_QUEUE` after `MAX_DELIVERIES` attempts instead of
looping forever.
"""

import threading
from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, Any, Protocol

from loguru import logger

if TYPE_CHECKING:
    from pika.adapters.blocking_connection import BlockingChannel, BlockingConnection

INGEST_QUEUE = "vlmscene.ingest"
CAPTION_QUEUE = "vlmscene.caption"
DEAD_LETTER_QUEUE = "vlmscene.dead"
DEAD_LETTER_EXCHANGE = "vlmscene.dead"
MAX_DELIVERIES = 3

# Carried in message headers so a request's logs can be followed across services.
REQUEST_ID_HEADER = "X-Request-ID"

# Seconds. pika's BlockingConnection only services heartbeats while it is pumping
# events, and it can't while a handler runs (captioning, loading a dataset), so a
# short heartbeat would get the connection dropped mid-handler.
_HEARTBEAT = 600

MessageHandler = Callable[[bytes, Mapping[str, str]], None]


class JobQueue(Protocol):
    """Anything that can publish messages to, and consume messages from, named queues."""

    def publish(self, queue: str, body: bytes, headers: Mapping[str, str] | None = None) -> None: ...

    def consume(self, queue: str, handler: MessageHandler, prefetch: int = 1) -> None:
        """Block, calling `handler` per message. A message is acked only if the handler returns."""
        ...

    def healthcheck(self) -> bool:
        """True if the broker is reachable."""
        ...


class RabbitMQJobQueue:
    """`JobQueue` backed by RabbitMQ. Constructing it never connects."""

    def __init__(self, url: str) -> None:
        self._url = url
        self._publisher: tuple[BlockingConnection, BlockingChannel] | None = None
        # BlockingConnection isn't thread-safe, and the API publishes from a threadpool.
        self._lock = threading.Lock()

    def publish(self, queue: str, body: bytes, headers: Mapping[str, str] | None = None) -> None:
        import pika
        from pika.exceptions import AMQPError

        with self._lock:
            _, channel = self._open_publisher()
            try:
                channel.basic_publish(
                    exchange="",
                    routing_key=queue,
                    body=body,
                    properties=pika.BasicProperties(
                        delivery_mode=pika.DeliveryMode.Persistent, headers=dict(headers or {})
                    ),
                )
            except AMQPError:
                # Drop the broken connection so the next call reconnects; the failure itself still propagates.
                self._close_publisher()
                raise

    def consume(self, queue: str, handler: MessageHandler, prefetch: int = 1) -> None:
        connection, channel = self._connect()
        try:
            channel.basic_qos(prefetch_count=prefetch)
            for method, properties, body in channel.consume(queue):
                if method is None or method.delivery_tag is None or properties is None or body is None:
                    raise RuntimeError(
                        "consume yielded an empty delivery"
                    )  # only happens on an inactivity timeout, which we never set
                headers: dict[str, str] = {str(key): str(value) for key, value in (properties.headers or {}).items()}
                try:
                    handler(body, headers)
                except Exception:
                    # Deliberately not re-raised: the nack makes the broker redeliver, and its
                    # delivery limit is what escalates a poison message to the dead-letter queue.
                    logger.exception("handler failed, nacking for redelivery")
                    channel.basic_nack(method.delivery_tag, requeue=True)
                else:
                    channel.basic_ack(method.delivery_tag)
        finally:
            if connection.is_open:
                connection.close()

    def healthcheck(self) -> bool:
        from pika.exceptions import AMQPError

        with self._lock:
            try:
                connection, _ = self._open_publisher()
                connection.process_data_events(time_limit=0)
            except (AMQPError, OSError) as exc:
                logger.warning("rabbitmq unreachable: {}", exc)
                self._close_publisher()
                return False
        return True

    def _open_publisher(self) -> "tuple[BlockingConnection, BlockingChannel]":
        if self._publisher is None or self._publisher[0].is_closed:
            connection, channel = self._connect()
            channel.confirm_delivery()  # raises on publish instead of silently losing a message
            self._publisher = (connection, channel)
        return self._publisher

    def _close_publisher(self) -> None:
        if self._publisher is not None and self._publisher[0].is_open:
            self._publisher[0].close()
        self._publisher = None

    def _connect(self) -> "tuple[BlockingConnection, BlockingChannel]":
        import pika

        parameters = pika.URLParameters(self._url)
        parameters.heartbeat = _HEARTBEAT
        connection = pika.BlockingConnection(parameters)
        channel = connection.channel()
        _declare_topology(channel)
        return connection, channel


def _declare_topology(channel: "BlockingChannel") -> None:
    """Idempotently declare every queue. Publishers and consumers both call this, so neither must start first."""
    channel.exchange_declare(DEAD_LETTER_EXCHANGE, exchange_type="fanout", durable=True)
    channel.queue_declare(DEAD_LETTER_QUEUE, durable=True, arguments={"x-queue-type": "quorum"})
    channel.queue_bind(DEAD_LETTER_QUEUE, DEAD_LETTER_EXCHANGE)

    arguments: dict[str, Any] = {
        "x-queue-type": "quorum",
        "x-delivery-limit": MAX_DELIVERIES,
        "x-dead-letter-exchange": DEAD_LETTER_EXCHANGE,
    }
    for queue in (INGEST_QUEUE, CAPTION_QUEUE):
        channel.queue_declare(queue, durable=True, arguments=arguments)
