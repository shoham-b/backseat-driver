"""The job store: the distributed write, and the job record that says when it is complete.

It lives in `transport/` because the seam forces it: it exists as soon as work becomes tasks, SQLite in the monolith and
Postgres across machines. The tables and queries it writes through are in `write/job_store/`.

The monolith's write step collects every description and writes one JSON file at the end. Once the work is split into
tasks, results arrive one at a time, in any order and possibly twice, and no process holds all of them. So the write is
incremental and idempotent: one row per description, in a store every worker and the API can reach.

Knowing when that write is done takes a record of what to expect. Ingest splits the job and records how many
descriptions it will produce; caption workers add them; the store aggregates, and a job is complete when the count
reaches the expectation. That is derived on every read, never stored, so there is no "mark complete" step to race.
The results and the job record are one store for that reason: the state is a comparison of the two.

    IngestWorker  ──set_expected_scenes──▶ ┐
    CaptionWorker ──record_description───▶ JobStore ◀──── API ◀──── show/
                                           (SQLite with the seam, Postgres across machines)
"""
