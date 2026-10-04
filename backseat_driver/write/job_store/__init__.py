"""The distributed write: one row per description, in a store every worker can reach.

The monolith's write step collects every description and writes one JSON file at the end. When workers run apart,
results arrive one at a time, in any order and possibly twice, so the write must be incremental and idempotent, and
whether a job is finished is derived from the counts instead of being a step someone performs.

    CaptionWorker ──record_description──▶ JobStore ◀──── API ◀──── show/
                                          (SQLite in the monolith, Postgres across machines)
"""
