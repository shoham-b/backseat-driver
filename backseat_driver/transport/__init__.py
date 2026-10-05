"""The seam between read and process: a queue, and the two workers at its ends.

Without it (`describe`) the program is one function call:

    read ──────────────────────────▶ process ──▶ write

With it, the same steps become tasks. `IngestWorker` is the read step turned into a producer and `CaptionWorker` is the
process and write steps run once per task:

    read ──▶ IngestWorker ══ queue ══▶ CaptionWorker ──▶ write
                          (this package)

The queue is a `JobQueue`. `InProcessJobQueue` keeps both ends in one process on one thread (the API monolith, so
`just dev` needs no broker). `CeleryJobQueue` puts RabbitMQ between them so the ends run on different machines.

Tasks finish one at a time, so the seam also brings a `JobStore` (`job_store/`, in this package): one row per
description plus the job's expected count, which is how a job knows it is done. It is a SQLite file in the monolith and
Postgres across machines. Only crossing machines needs `read/s3/`, because the workers then share no disk.
"""
