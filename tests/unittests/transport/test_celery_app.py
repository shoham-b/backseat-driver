from backseat_driver.transport.celery_app import (
    CAPTION_QUEUE,
    CAPTION_TASK,
    INGEST_QUEUE,
    INGEST_TASK,
    MAX_RETRIES,
    make_celery_app,
)

BROKER = "amqp://guest:guest@broker:5672/"


def test_celery_app_is_configured_for_durable_at_least_once_delivery() -> None:
    conf = make_celery_app(BROKER).conf

    assert conf.broker_url == BROKER
    assert conf.task_acks_late is True
    assert conf.task_reject_on_worker_lost is True
    assert conf.worker_prefetch_multiplier == 1
    assert conf.task_ignore_result is True
    assert conf.broker_transport_options == {"confirm_publish": True}
    assert conf.worker_enable_remote_control is False


def test_celery_app_declares_both_queues_as_quorum_queues() -> None:
    queues = {q.name: q for q in make_celery_app(BROKER).conf.task_queues}

    assert set(queues) == {INGEST_QUEUE, CAPTION_QUEUE}
    assert all(q.queue_arguments == {"x-queue-type": "quorum"} for q in queues.values())
    assert all(q.routing_key == q.name for q in queues.values())


def test_tasks_are_routed_to_their_own_queues() -> None:
    routes = make_celery_app(BROKER).conf.task_routes

    assert routes == {INGEST_TASK: {"queue": INGEST_QUEUE}, CAPTION_TASK: {"queue": CAPTION_QUEUE}}


def test_max_retries_is_bounded() -> None:
    assert MAX_RETRIES > 0
