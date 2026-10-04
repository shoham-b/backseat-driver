"""Run exactly one queued task, for the run-to-completion Jobs that `worker ingest --once` starts (one Job per task).

A Celery worker can't do this: it prefetches, so it can start the next message before it has noticed it should stop.
Here the message is fetched with a plain `basic_get`, run in this process through its registered task (retries
included, without backoff), and acked only afterwards, so a Job that dies mid-task leaves the message for the next one.
A task that still fails after its retries is dropped, like the Celery workers do, rather than redelivered forever.
"""

from typing import Any

from loguru import logger


def consume_one(app: Any, queue_name: str) -> bool:
    """Handle at most one message from `queue_name`. False if it was empty; raises if the task failed."""
    # An eager retry looks its task up on the current app, which must be this one.
    app.set_current()
    with app.connection_for_read() as connection:
        queue = app.amqp.queues[queue_name](connection.default_channel)
        queue.declare()
        message = queue.get(no_ack=False)
        if message is None:
            logger.info("no queued task")
            return False

        args, kwargs, _ = message.decode()
        result = app.tasks[message.headers["task"]].apply(args=args, kwargs=kwargs, task_id=message.headers["id"])
        message.ack()
        if not result.successful():
            raise RuntimeError(f"task {message.headers['task']} failed and was dropped") from result.result
        return True
