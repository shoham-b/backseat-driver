"""The seam between read and process: a queue, and the two workers at its ends.

Without it (`describe`) the program is one function call:

    read ──────────────────────────▶ process ──▶ write

With it, the same steps become tasks. `IngestWorker` is the read step turned into a producer and `CaptionWorker` is the
process and write steps run once per task:

    read ──▶ IngestWorker ══ queue ══▶ CaptionWorker ──▶ write
                          (this package)

The queue is a `JobQueue`. `InProcessJobQueue` keeps both ends in one process on one thread (the API monolith, so
`just dev` needs no broker). `CeleryJobQueue` puts RabbitMQ between them so the ends run on different machines, and
only then are `read/s3/` (the images) and `write/job_store/` (the results) needed.
"""
