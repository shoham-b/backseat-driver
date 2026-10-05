"""Stage 3, write: persist the `SceneDescription`s.

    describe (one process)   list[SceneDescription] ──▶ json_writer.write_json ──▶ output/*.json
    workers (many machines)  one SceneDescription   ──▶ job_store.JobStore     ──▶ SQLite / Postgres

The two are different contracts: a batch written once at the end, and results recorded one by one. The second also
carries the completion rule: the job record says how many results to expect, so "is it done" is derived from the
count. `show/` reads either and is not part of this stage.
"""
